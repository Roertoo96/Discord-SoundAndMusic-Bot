import os
import platform


def perform_os_specific_action():
    current_os = platform.system()

    if current_os == "Windows":
        media = r"C:/Users/Andre/OneDrive/Github/PROST/media/"
        token = os.getenv('discordbot')
        return media, token
        # Hier den Code für Windows hinzufügen

    elif current_os == "Darwin":  # "Darwin" ist der Systemname für macOS
        media = './media/'
        token = os.environ.get('discordbot')
        return media, token
        # Hier den Code für macOS hinzufügen

    else:
        media = './media/'
        token = os.environ.get('discordbot')
        passwordpavsrv = os.environ.get('pav')
        return media, token, passwordpavsrv

# Media Variable setzen
media,token = perform_os_specific_action()