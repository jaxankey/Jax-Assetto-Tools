call C:/Users/Jack/miniconda3/Scripts/activate.bat C:/Users/Jack/miniconda3
pyinstaller --noconfirm --onefile --windowed --splash "./splash/splash.png" --distpath "." "./uploader.py"
rem auto-py-to-exe
del uploader.spec
rmdir /s/q build
@pause