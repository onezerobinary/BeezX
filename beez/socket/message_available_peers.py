"""Beez blockchain - available peers message"""

from __future__ import annotations
from typing import TYPE_CHECKING, List

from beez.socket.message import Message
from beez.socket.message_type import MessageType

if TYPE_CHECKING:
    from beez.socket.socket_connector import SocketConnector


class MessageAvailablePeers(Message):  # pylint: disable=too-few-public-methods
    """Available peers message"""

    def __init__(
        self,
        sender_connector: SocketConnector,
        message_type: MessageType,
        available_peers: dict[str,int]
    ):
        super().__init__(sender_connector, message_type)
        self.available_peers = available_peers
