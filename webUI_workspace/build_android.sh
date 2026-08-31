#!/bin/bash

echo "=== Building Android App ==="
echo ""

cd "$(dirname "$0")"

if [ ! -f "capacitor.config.json" ]; then
    echo "Error: capacitor.config.json not found"
    exit 1
fi

echo "Step 1: Install dependencies..."
npm install @capacitor/core @capacitor/cli @capacitor/android @capacitor/camera 2>/dev/null || true

echo ""
echo "Step 2: Sync with Android..."
npx cap sync android

echo ""
echo "Step 3: Build debug APK..."
cd android
./gradlew assembleDebug
cd ..

echo ""
echo "=== Build Complete ==="
echo "APK located at: android/app/build/outputs/apk/debug/app-debug.apk"

echo ""
echo "To install on device:"
echo "  adb install android/app/build/outputs/apk/debug/app-debug.apk"