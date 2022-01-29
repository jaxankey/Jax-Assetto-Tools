
:: Copy content from the liveries google drive folder to the Assetto corsa content directory, skipping desktop.ini files
robocopy "C:\path\to\google\drive\uncompressed\liveries\content" "C:\path\to\SteamLibrary\steamapps\common\assettocorsa\content" /s /e /is /xf desktop.ini

:: Delete the existing liveries archive from the public google drive folder
del /f "C:\path\to\google\drive\compressed\Liveries.7z"

:: Launch asynchronous process to compress the liveries into a 7z file for people to download, again excluding desktop.ini
start "Compressing Liveries" 7z -mx7 -xr!*desktop.ini a "C:\Users\Jack\My Drive (sankey.childress@gmail.com)\LoPeN\LoPeN Liveries.7z" "C:\Users\Jack\My Drive (sankey.childress@gmail.com)\Liveries\content"