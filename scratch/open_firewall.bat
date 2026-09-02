@echo off
echo Autorisation du port 8765 dans le pare-feu Windows pour le serveur...
netsh advfirewall firewall add rule name="CabinetNotarial_Port_8765" dir=in action=allow protocol=TCP localport=8765
echo.
echo Operation terminee ! Vous pouvez fermer cette fenetre.
pause
