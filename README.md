# sixseven-project
這是一群飛修人和一個電子人的專題

## Jetson Orin Nano

```text
1. 這是什麼
2. 可以幹嘛
3. 怎麼開機
4. 這個什麼鬼系統怎麼用
```

### 1. 這是什麼

Jetson Orin Nano 是由NVIDIA所推出的一塊高性能開發版

### 2. 可以幹嘛

Jetson 系列在邊緣運算與機器人等領域深耕多年，Jetson常被用來運行AI相關的服務，或者做為機器人競賽等領域使用，而Jetson Orin Nano等系列是最常見的型號

### 3.怎麼開機

首先理所當然，他是一塊SBC，所以鍵盤滑鼠電源螢幕還是要的，在開機之前你必須要確定裡面有系統，建議使用Jetson的L4T或Ubuntu

[L4T 下載 (24.1GB)](https://developer.nvidia.com/downloads/embedded/L4T/r36_Release_v4.4/jp62-r1-orin-nano-sd-card-image.zip)  
[Ubuntu Server]

### 4. 這個什麼鬼系統怎麼用

首先，如果這是你剛燒完卡剛開機  
你必須先配置:  

```text
1. 語言
2. 網路連線(用於系統更新)
3. 使用者名稱
4. 是否安裝Chromuim
5. 地區
```  

順序可能有錯但不外乎就這幾個  
然後進到桌面之後首先先更新系統再來安裝瀏覽器(Linux用戶大多使用Firefox)  

1. 更新系統

    ```sh
    sudo apt-get update
    sudo apt-get upgrade
    ```  

2. 安裝firefox

    ```sh
    sudo apt-get install firefox
    ```

    >Tips: 這個時候如果發生無法reach snap的話可以嘗試使用flatpak解  

    ```sh
    sudo apt update
    # 安裝flatpak以及加入flathub的Repositroy
    sudo apt install flatpak
    flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
    
    # 安裝firefox
    flatpak install flathub org.mozilla.firefox
    ```


