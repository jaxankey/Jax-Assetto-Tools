call C:/Users/Jack/Miniconda3/Scripts/activate.bat C:/Users/Jack/Miniconda3
pyinstaller --onefile --distpath . uploader.pyw
del uploader.spec
rmdir /s/q build
rmdir /s/q __pycache__
@pause