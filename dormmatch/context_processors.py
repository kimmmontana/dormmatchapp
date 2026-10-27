from django.conf import settings

from . import stellar


def stellar_settings(request):
    return {
        "stellar_enabled": stellar.is_enabled(),
        "stellar_network_passphrase": settings.STELLAR_NETWORK_PASSPHRASE,
        "stellar_explorer_url": settings.STELLAR_EXPLORER_URL,
    }
