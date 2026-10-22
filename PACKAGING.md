# Packaging the controller for Windows

## For someone who just wants to run it

1. Unzip `MartinVDOController-windows.zip` anywhere (for example to the Desktop).
2. Open the `MartinVDOController` folder and double-click `MartinVDOController.exe`.

No Python install is needed. Settings are saved in `settings.json` next to the .exe, so keep the folder
somewhere you can write to (not Program Files).

The first time it runs, Windows may ask whether to allow it through the firewall (it needs UDP for Art-Net,
sACN and OSC). Allow it on private networks. Windows SmartScreen may also warn that the app is from an
unknown publisher, because it isn't code-signed. Choose "More info" and then "Run anyway".

## Building the package (on the development PC)

From the project folder:

```bat
.venv\Scripts\python -m pip install -r requirements-build.txt
.venv\Scripts\python -m PyInstaller --noconfirm --windowed --name MartinVDOController ^
    --distpath dist --workpath build --specpath build run_controller.py
```

The app is written to `dist\MartinVDOController\`. To make a download, zip that folder, for example:

```powershell
Compress-Archive -Path dist\MartinVDOController -DestinationPath dist\MartinVDOController-windows.zip -Force
```

Rebuild after any code change. The build is about 110 MB, mostly Qt.
