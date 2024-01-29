import os
import platform


def perform_os_specific_action():
    current_os = platform.system()
    media = './media/'
    token = os.environ.get('discordbot')
    passwordpavsrv = os.environ.get('pav')

    if current_os == "Windows":
        media = r"C:/Users/Andre/OneDrive/Github/PROST/media/"
    elif current_os == "Darwin":  # macOS
        media = './media/'
    
    return media, token, passwordpavsrv

# Media Variable setzen
media,token,passwordpavsrv = perform_os_specific_action()