#! /bin/bash
systemctl stop kodi
unzip -o ~/plugin.video.koditox.zip
systemctl start kodi
sleep 5
kodi-send --action="ActivateWindow(Videos, plugin://plugin.video.koditox/)"
sleep 3
kodi-send --action="RunPlugin(plugin://plugin.video.koditox/?action=start)"
