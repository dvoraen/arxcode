"""
Notifier.py

Contains classes for various forms of notifying players, PC GMs, staff, and
so on.  The purpose of these classes is to reduce code for sending messages
to specific subsets of the game.  (e.g. - send only to staff in a given room)


USAGE

The base Notifier class supports the following (boolean) to_flags arguments,
each of which default to False if not found in the to_flags argument:

* to_player - this notifier sends to non-gm players
* to_gm - this notifier sends to gm players
* to_staff - this notifier sends to staff players

Subclasses of Notifier differ in how they source characters, which is why
it is required to override _source_characters() when deriving from Notifier.

INHERITANCE TREE

Notifier
- RoomNotifier
- ListNotifier
    - SelfListNotifier

EXAMPLE CODE

# This code will send "Hello, world!" to all player GMs
# and staff in the given room.
gm_notifier = RoomNotifier(
    caller,
    room=caller.location,
    to_gm=True,
    to_staff=True
)
gm_notifier.generate()
gm_notifier.notify("Hello, world!")
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional


class NotifyError(Exception):
    pass


class Notifier(ABC):
    """
    Abstract base class for sending notifications to the game.
    This class is meant to be derived from and its 'protected' code
    utilized in derived classes (to lower code duplication).
    """

    def __init__(
        self,
        caller,
        **to_flags,
    ):
        self.caller = caller
        self.to_flags = to_flags

        self.player_set = set()
        self.gm_set = set()
        self.staff_set = set()

        self.receiver_set = set()

    def generate(self):
        """Generates the receiver list for this notifier."""
        self._source_characters()
        self._filter_receivers()

    def notify(self, msg: str, options: Optional[Dict[str, bool]] = None):
        """Notifies each receiver of msg with the given options, if any."""
        for rcvr in self.receiver_set:
            rcvr.msg(msg, options)

    @property
    def receivers(self) -> set:
        return self.receiver_set

    @property
    def player_names(self) -> List[str]:
        return [str(player) for player in self.player_set]

    @property
    def gm_names(self) -> List[str]:
        return [str(gm) for gm in self.gm_set]

    @property
    def staff_names(self) -> List[str]:
        return [str(staff) for staff in self.staff_set]

    @property
    def receiver_names(self) -> List[str]:
        return [str(player) for player in self.receiver_set]

    @abstractmethod
    def _source_characters(self):
        pass

    def _filter_players(self):
        """Returns all non-gm, non-staff players in receiver_set."""
        self.player_set = {
            char for char in self.receiver_set if not char.check_staff_or_gm()
        }

    def _filter_gms(self):
        """Returns all player GMs in receiver_set."""
        self.gm_set = {char for char in self.receiver_set if char.is_gm()}

    def _filter_staff(self):
        """Returns all staff in receiver_set."""
        self.staff_set = {char for char in self.receiver_set if char.is_staff()}

    def _filter_receivers(self):
        """Returns all receivers designated by the given receiver flags."""
        if self.to_flags.get("to_player", False):
            self._filter_players()

        if self.to_flags.get("to_gm", False):
            self._filter_gms()

        if self.to_flags.get("to_staff", False):
            self._filter_staff()

        self.receiver_set = self.player_set | self.gm_set | self.staff_set


class RoomNotifier(Notifier):
    """
    Notifier for sending to everyone in a room, filtered by
    the to_flags.
    """

    def __init__(
        self,
        caller,
        room,
        **to_flags,
    ):
        super().__init__(caller, **to_flags)
        self.room = room

    def _source_characters(self):
        """
        Generates the source receiver list from all characters
        in the given room.
        """
        if self.room:
            self.receiver_set = {
                char for char in self.room.contents if char.is_character
            }


class ListNotifier(Notifier):
    """
    Notifier for sending only to the passed in list of receivers,
    then filtered by the to_flags.

    NOTE: The caller is not notified when using ListNotifier.  Use
    SelfListNotifier to get this behavior.
    """

    def __init__(self, caller, receivers: List[str] = None, **to_flags):
        super().__init__(caller, **to_flags)

        self.receiver_list = receivers or []

    def _source_characters(self):
        for name in self.receiver_list:
            receiver = self.caller.search(name, use_nicks=True)
            if receiver:
                self.receiver_set.add(receiver)


class SelfListNotifier(ListNotifier):
    """
    Notifier for sending only to the passed in list of receivers and
    the caller, then filtered by the to_flags.
    """

    def __init__(
        self,
        caller,
        receivers: List[str],
        **to_flags,
    ):
        super().__init__(caller, receivers, **to_flags)

    def _source_characters(self) -> set:
        """Generates the source receiver list from passed in receivers."""
        super()._source_characters()

        # Caller always sees their notifications in this notifier if
        # they're part of the to_flags set.
        self.receiver_set.add(self.caller)
