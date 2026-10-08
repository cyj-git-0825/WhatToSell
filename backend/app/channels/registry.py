from app.channels.base import ChannelAdapter
from app.models import Channel

_adapters: dict[Channel, ChannelAdapter] = {}


def register(adapter: ChannelAdapter) -> None:
    _adapters[adapter.channel] = adapter


def get_adapter(channel: Channel) -> ChannelAdapter:
    try:
        return _adapters[channel]
    except KeyError:
        raise LookupError(f"No adapter registered for channel {channel!r}") from None


def available_channels() -> list[Channel]:
    return list(_adapters)
