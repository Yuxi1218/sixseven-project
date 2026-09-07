"""WebRTC 串流模組：完整雙向。
- 手機上游：raw MediaStream 相機幀 → 後端（不逐幀 toBlob/base64/fetch）
- 後端連續推理：消費上游幀 → 更新 annotated_frame
- 手機下游：annotated 幀走 NVENC 硬體編碼推給手機 <video> 顯示
如同 DMA：鏡頭資料旁路主處理，每幀不經手機 encode。
"""
import asyncio
import json
import logging
import time

from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from aiortc.mediastreams import VIDEO_TIME_BASE, convert_timebase, VideoFrame
import numpy as np
import cv2

logger = logging.getLogger("webrtc")

_peers = set()
_upstream_img = None          # 最近手機上游相機幀 (BGR ndarray)
_upstream_seq = 0             # 每次新幀 +1，供推理 loop 去重
_upstream_new = 0            # (保留)
_frame_lock = None            # asyncio.Lock
_downstream_getter = None     # () -> BGR frame 給下游推流
_data_channels = set()        # 開放中的 data channel（推送偵測框資料）
_loop = None                  # aiortc 所在的 asyncio event loop


def init(frame_getter):
    """初始化：設定下游幀來源 getter 與鎖。在事件迴圈中呼叫。"""
    global _downstream_getter, _frame_lock
    _downstream_getter = frame_getter
    if _frame_lock is None:
        _frame_lock = asyncio.Lock()


def get_upstream_frame_newest():
    """回傳最新上游相機幀（非阻塞）。"""
    global _upstream_img
    return _upstream_img


def get_upstream_seq():
    return _upstream_seq


def push_detections(payload):
    """把推理結果（歸一化框+標籤）廣播給手機的 data channel。可從非 asyncio 執行緒呼叫。"""
    if not _data_channels or _loop is None:
        return
    msg = json.dumps(payload)
    # data channel 非 thread-safe：改在 aiortc event loop 執行緒上送出
    _loop.call_soon_threadsafe(_send_all, msg)


class AnnotatedFrameTrack(VideoStreamTrack):
    """下游：取 annotated 幀，縮放至高畫質後推流。"""

    def __init__(self, fps=28, out_width=1280, out_height=960):
        super().__init__()
        self._fps = fps
        self._start = time.monotonic()
        self._idx = 0
        self._out_w = out_width
        self._out_h = out_height

    async def recv(self):
        target = self._start + (self._idx / self._fps)
        now = time.monotonic()
        if target > now:
            await asyncio.sleep(target - now)
        self._idx += 1

        img = _downstream_getter() if _downstream_getter else None
        if img is None or (hasattr(img, 'size') and img.size == 0):
            img = np.zeros((self._out_h, self._out_w, 3), dtype=np.uint8)
        elif isinstance(img, bytes):
            nparr = np.frombuffer(img, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                img = np.zeros((self._out_h, self._out_w, 3), dtype=np.uint8)
        if img.ndim == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        # 畫質提升：若上游解析度小於 HD 目標則向上放大；已是高解析度則維持原尺寸
        if img.shape[1] < 1280:
            scale = max(1280 / img.shape[1], 960 / img.shape[0])
            new_w = int(round(img.shape[1] * scale / 2) * 2)
            new_h = int(round(img.shape[0] * scale / 2) * 2)
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        rgb = np.ascontiguousarray(img[:, :, ::-1])
        # 設定正確 pts + time_base（90kHz / 1/30s），否則瀏覽器 H264 解碼器拿不到可解幀而全黑
        frame = VideoFrame.from_ndarray(rgb, format="rgb24")
        frame.pts = convert_timebase(self._idx, self._fps, VIDEO_TIME_BASE)
        frame.time_base = VIDEO_TIME_BASE
        return frame


async def _consume_upstream(track):
    """消費手機上游相機幀，存入共享 _upstream_img。"""
    global _upstream_img, _upstream_seq
    got = 0
    while True:
        try:
            frame = await track.recv()
        except Exception:
            break
        try:
            img = frame.to_ndarray(format="rgb24")
            _upstream_img = img[:, :, ::-1].copy()  # RGB -> BGR
            _upstream_seq += 1
            got += 1
            if got == 1 or got % 50 == 0:
                print(f"[webrtc] 上游已收 {got} 幀 (seq={_upstream_seq}) 尺寸={img.shape[1]}x{img.shape[0]}")
        except Exception as e:
            print(f"[webrtc] upstream decode err: {e}")
        await asyncio.sleep(0)


def _send_all(msg):
    """在 aiortc loop 執行緒執行：把 msg 送到所有 open data channel。"""
    for ch in list(_data_channels):
        try:
            if ch.readyState == "open":
                ch.send(msg)
        except Exception:
            _data_channels.discard(ch)


async def create_offer():
    """建立 pc：下游推 annotated；上游等手機相機 track。等 ICE gathering 完成後回傳完整 SDP。"""
    global _loop
    _loop = asyncio.get_running_loop()
    pc = RTCPeerConnection()
    _peers.add(pc)

    pc.addTrack(AnnotatedFrameTrack())
    # 建立 data channel：手機端接收偵測框座標+標籤（做法A：原生畫質疊框）
    dc = pc.createDataChannel("detections")
    _data_channels.add(dc)

    @pc.on("datachannel")
    def _on_datachannel(channel):
        print(f"[webrtc] data channel: {channel.label} (id={channel.id})")
        _data_channels.add(channel)

    @pc.on("track")
    def _on_track(track):
        print(f"[webrtc] upstream track: {track.kind}")
        if track.kind == "video":
            asyncio.ensure_future(_consume_upstream(track))

    @pc.on("connectionstatechange")
    async def _on_state():
        print(f"[webrtc] state={pc.connectionState}")
        if pc.connectionState in ("failed", "closed", "disconnected"):
            _peers.discard(pc)
            _data_channels.clear()  # 此 pc 關閉，清掉所有 data channel（單一 peer 場景）
            _notify_peer_closed()

    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)

    # 等 ICE gathering 完成，確保 host candidate 併入 SDP（LAN 直連不需 trickle）
    if pc.iceGatheringState != "complete":
        done = asyncio.Event()
        pc.on("icegatheringstatechange", lambda: done.set())
        try:
            await asyncio.wait_for(done.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            pass

    sdp = pc.localDescription.sdp if pc.localDescription else offer.sdp
    return sdp, pc


async def set_answer(pc, answer_sdp):
    answer = RTCSessionDescription(sdp=answer_sdp, type="answer")
    await pc.setRemoteDescription(answer)
    # 診斷：查看對端 transceiver direction & 是否有 receiver
    for tr in pc.getTransceivers():
        print(f"[webrtc] transceiver mid={tr.mid} direction={tr.direction} "
              f"receiver={tr.receiver is not None} sender={tr.sender is not None} "
              f"recv_track={tr.receiver.track.kind if tr.receiver and tr.receiver.track else '無'}")


async def close_peer(pc):
    await pc.close()
    _peers.discard(pc)


_peer_closed_callback = None


def set_peer_closed_callback(cb):
    """所有 peer 關閉時回呼（供停止連續推理環，釋放 GPU）。"""
    global _peer_closed_callback
    _peer_closed_callback = cb


def _notify_peer_closed():
    if not _peers and _peer_closed_callback:
        _peer_closed_callback()