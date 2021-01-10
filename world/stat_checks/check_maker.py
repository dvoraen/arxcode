from random import choice, randint
from functools import total_ordering

from world.conditions.modifiers_handlers import ModifierHandler
from world.stat_checks.models import (
    DifficultyRating,
    RollResult,
    StatWeight,
    NaturalRollType,
    StatCheck,
)

from server.utils.notifier import RoomNotifier, SelfListNotifier


# RawRoll / SimpleRoll public interface
# (reference of calls for overloading)
# =======
# METHODS
# =======

# execute()
# - get_roll_value_for traits()
#     - get_roll_value_for_stat()
#     - get_roll_value_for_skill()
# - get_roll_value_for_rating()
# - check_for_crit_or_botch()
# - get_roll_value_for_knack()
# - get_context()

# ==========
# PROPERTIES
# ==========

# is_crit
# is_botch
# is_success

# roll_message
# - roll_prefix
#     - check_string


TIE_THRESHOLD = 5


def check_rolls_tied(roll1, roll2, tie_value=TIE_THRESHOLD):
    if roll1.roll_result_object != roll2.roll_result_object:
        return False
    return abs(roll1.result_value - roll2.result_value) < tie_value


def get_check_string(stat, skill, rating) -> str:
    if skill:
        return f"{stat} and {skill} at {rating}"
    return f"{stat} at {rating}"


class BaseRoll:
    """
    A BaseRoll is a die roll of a given stat (and skill if applicable)
    that is modified only by a knack for it, and it determines whether
    the roll is a crit/botch.

    Modifications to the roll due to difficulty rating and other
    factors are done in subclasses.
    """

    def __init__(self, character=None, stat: str = None, skill: str = None):
        self.character = character
        self.stat = stat
        self.skill = skill
        self.raw_roll = 0
        self.full_roll = 0
        self.natural_roll_type: NaturalRollType = None

    def execute(self):
        """Generates the unmodified base roll."""
        self.raw_roll = randint(1, 100)
        traits_value = self.get_roll_value_for_traits()
        knack_value = self.get_roll_value_for_knack()

        self.full_roll = self.raw_roll + traits_value + knack_value

        self.natural_roll_type = self.check_for_crit_or_botch()

    def get_roll_value_for_traits(self) -> int:
        """Returns the total for stat and skill contribution to this roll."""
        stat_value = self.get_roll_value_for_stat()
        skill_value = self.get_roll_value_for_skill()

        return stat_value + skill_value

    def get_roll_value_for_stat(self) -> int:
        """
        Looks up how much to modify our roll by based on our stat. We use a lookup table to
        determine how much each level of the stat is weighted by. Weight may be different if
        there is no skills for this roll.
        """
        if not self.stat:
            return 0
        base = self.character.traits.get_stat_value(self.stat)
        # if we don't have a skill defined, we're rolling stat alone, and the weight may be different
        only_stat = not self.skill
        return StatWeight.get_weighted_value_for_stat(base, only_stat)

    def get_roll_value_for_skill(self) -> int:
        """
        Looks up how much to modify our roll based on our skill. We use a lookup table to
        determine how much each level of the skill is weighted by.
        """
        if not self.skill:
            return 0
        base = self.character.traits.get_skill_value(self.skill)
        return StatWeight.get_weighted_value_for_skill(base)

    def get_roll_value_for_knack(self) -> int:
        """Looks up the value for the character's knacks, if any."""
        try:
            mods: ModifierHandler = self.character.mods
            base = mods.get_total_roll_modifiers([self.stat], [self.skill])
        except AttributeError:
            return 0
        return StatWeight.get_weighted_value_for_knack(base)

    def check_for_crit_or_botch(self):
        """
        Checks our lookup table with our raw roll and sees if we got a crit or botch.
        """
        return NaturalRollType.get_roll_type(self.raw_roll)

    def get_context(self) -> dict:
        crit, botch = self._get_context_crit_botch()

        return {
            "character": self.character,
            "roll": self.full_roll,
            "crit": crit,
            "botch": botch,
        }

    @property
    def is_crit(self) -> bool:
        if not self.natural_roll_type:
            return False
        return self.natural_roll_type.is_crit

    @property
    def is_botch(self) -> bool:
        if not self.natural_roll_type:
            return False
        return self.natural_roll_type.is_botch

    def _get_context_crit_botch(self):
        crit = None
        botch = None
        if self.natural_roll_type:
            if self.natural_roll_type.is_crit:
                crit = self.natural_roll_type
            else:
                botch = self.natural_roll_type

        return crit, botch


@total_ordering
class SimpleRoll(BaseRoll):
    def __init__(
        self,
        character=None,
        stat: str = None,
        skill: str = None,
        rating: DifficultyRating = None,
        tie_threshold: int = TIE_THRESHOLD,
        **kwargs,
    ):
        super().__init__(character, stat, skill)

        self.rating = rating
        self.result_value: int = None
        self.result_message = None
        self.room = character and character.location
        self.roll_result_object: RollResult = None
        self.tie_threshold = tie_threshold
        self.roll_kwargs = kwargs

    def __lt__(self, other: "SimpleRoll"):
        """
        We treat a roll as being less than another if the Result is lower,
        or same result is outside tie threshold for the result values.
        """
        try:
            if self.roll_result_object == other.roll_result_object:
                return (self.result_value + self.tie_threshold) < other.result_value
            return self.roll_result_object.value < other.roll_result_object.value
        except AttributeError:
            return NotImplemented

    def __eq__(self, other: "SimpleRoll"):
        """Equal if they have the same apparent result object and the """
        return (self.roll_result_object == other.roll_result_object) and abs(
            self.result_value - other.result_value
        ) <= self.tie_threshold

    def execute(self):
        """Does the actual roll"""
        super().execute()

        rating_value = self.get_roll_value_for_rating()
        self.result_value = self.full_roll - rating_value

        self.roll_result_object = RollResult.get_instance_for_roll(
            self.result_value, natural_roll_type=self.natural_roll_type
        )
        self.result_message = self.roll_result_object.render(**self.get_context())

    def get_roll_value_for_rating(self) -> int:
        return self.rating.value

    def get_context(self) -> dict:
        crit, botch = self._get_context_crit_botch()

        return {
            "character": self.character,
            "roll": self.result_value,
            "result": self.roll_result_object,
            "natural_roll_type": self.natural_roll_type,
            "crit": crit,
            "botch": botch,
        }

    @property
    def is_success(self) -> bool:
        return self.roll_result_object.is_success

    @property
    def check_string(self) -> str:
        if self.skill:
            return f"{self.stat} and {self.skill} at {self.rating}"
        return f"{self.stat} at {self.rating}"

    @property
    def roll_prefix(self) -> str:
        return f"{self.character} checks {self.check_string}."

    @property
    def roll_message(self) -> str:
        return f"{self.roll_prefix} {self.result_message}"


class DefinedRoll(SimpleRoll):
    """
    Roll for a pre-created check that's saved in the database, which will be used
    to populate the values for the roll.
    """

    def __init__(self, character, check: StatCheck = None, target=None, **kwargs):
        super().__init__(character, **kwargs)
        self.check = check
        # target is the value that determines difficulty rating
        self.target = target or character

    def get_roll_value_for_traits(self) -> int:
        """
        Get the value for our traits from our check
        """
        return self.check.get_value_for_traits(self.character)

    def get_roll_value_for_rating(self) -> int:
        """
        Get the value for the difficult rating from our check
        """
        if self.rating:
            return super().get_roll_value_for_rating()
        self.rating = self.check.get_difficulty_rating(self.target, **self.roll_kwargs)
        return self.rating.value

    def get_roll_value_for_knack(self) -> int:
        """Looks up the value for the character's knacks, if any."""
        # get stats and skills for our check
        try:
            mods: ModifierHandler = self.character.mods
            base = mods.get_total_roll_modifiers(
                self.check.get_stats_list(), self.check.get_skills_list()
            )
        except AttributeError:
            return 0
        return StatWeight.get_weighted_value_for_knack(base)

    @property
    def outcome(self):
        return self.check.get_outcome_for_result(self.roll_result_object)

    @property
    def roll_prefix(self):
        roll_message = f"{self.character} checks '{self.check}' at {self.rating}."
        return roll_message


class SpoofRoll(SimpleRoll):
    def __init__(
        self,
        character=None,
        stat: str = None,
        stat_value: int = 0,
        skill: str = None,
        skill_value: int = 0,
        rating: DifficultyRating = None,
        npc_name: str = None,
        **kwargs,
    ):
        super().__init__(character, stat, skill, rating, **kwargs)
        self.stat_value = stat_value
        self.skill_value = skill_value
        self.npc_name = npc_name

        self.can_crit = kwargs.get("can_crit", False)
        self.is_flub = kwargs.get("is_flub", False)

    def execute(self):
        stat_value = self.get_roll_value_for_stat()
        skill_value = self.get_roll_value_for_skill()
        rating_value = self.get_roll_value_for_rating()

        # Flub rolls are botched rolls.
        if self.is_flub:
            self.raw_roll = 1
        else:
            self.raw_roll = randint(1, 100)

        # Unlike RawRoll/SimpleRoll, SpoofRoll does not take knacks
        # into account. (NPCs generally don't have knacks)
        self.result_value = self.raw_roll + stat_value + skill_value - rating_value

        # GMCheck rolls don't crit/botch by default
        if self.can_crit or self.is_flub:
            self.natural_roll_type = self.check_for_crit_or_botch()
        else:
            self.natural_roll_type = None

        # If the roll is a flub, get the failed roll objects and pick one
        # at random for our resulting roll.
        if self.is_flub:
            fail_rolls = self.__get_fail_rolls()
            self.roll_result_object = choice(fail_rolls)
        else:
            self.roll_result_object = RollResult.get_instance_for_roll(
                self.result_value, natural_roll_type=self.natural_roll_type
            )

        self.result_message = self.roll_result_object.render(**self.get_context())

    def get_roll_value_for_stat(self) -> int:
        if not self.stat:
            return 0

        only_stat = not self.skill
        return StatWeight.get_weighted_value_for_stat(self.stat_value, only_stat)

    def get_roll_value_for_skill(self) -> int:
        if not self.skill:
            return 0

        return StatWeight.get_weighted_value_for_skill(self.skill_value)

    def get_context(self) -> dict:
        crit, botch = self._get_context_crit_botch()

        if self.npc_name:
            name = self.npc_name
        else:
            name = self.character

        return {
            "character": name,
            "roll": self.result_value,
            "result": self.roll_result_object,
            "natural_roll_type": self.natural_roll_type,
            "crit": crit,
            "botch": botch,
        }

    def __get_fail_rolls(self):
        rolls = RollResult.get_all_cached_instances()
        if not rolls:
            return RollResult.objects.filter(value__lt=0)
        else:
            return [obj for obj in rolls if obj.value < 0]

    @property
    def spoof_check_string(self) -> str:
        if self.skill:
            return f"{self.stat} ({self.stat_value}) and {self.skill} ({self.skill_value}) at {self.rating}"
        return f"{self.stat} ({self.stat_value}) at {self.rating}"

    @property
    def npc_roll_prefix(self) -> str:
        return f"{self.character} GM checks |c{self.npc_name}'s|n {self.spoof_check_string}."

    @property
    def roll_prefix(self) -> str:
        return f"|c{self.character}|n GM checks {self.spoof_check_string}."

    @property
    def roll_message(self) -> str:
        if self.npc_name:
            return f"{self.npc_roll_prefix} {self.result_message}"
        return f"{self.roll_prefix} {self.result_message}"


class RetainerRoll(SimpleRoll):
    def __init__(
        self,
        character=None,
        retainer=None,
        stat: str = None,
        skill: str = None,
        rating: DifficultyRating = None,
        **kwargs,
    ):
        super().__init__(
            character=character,
            stat=stat,
            skill=skill,
            rating=rating,
            **kwargs,
        )

        self.retainer = retainer

    def get_roll_value_for_stat(self) -> int:
        if not self.stat or not self.retainer:
            return 0

        stat_val = self.retainer.dbobj.traits.get_stat_value(self.stat)
        return StatWeight.get_weighted_value_for_stat(stat_val, not self.skill)

    def get_roll_value_for_skill(self) -> int:
        if not self.skill or not self.retainer:
            return 0

        skill_val = self.retainer.dbobj.traits.get_skill_value(self.skill)
        return StatWeight.get_weighted_value_for_skill(skill_val)

    def get_context(self) -> dict:
        crit, botch = self._get_context_crit_botch()
        short_name = self.__split_retainer_name()

        return {
            "character": short_name,
            "roll": self.result_value,
            "natural_roll_type": self.natural_roll_type,
            "result": self.roll_result_object,
            "crit": crit,
            "botch": botch,
        }

    @property
    def roll_prefix(self) -> str:
        return f"{self.character}'s retainer ({self.retainer.pretty_name}|n) checks {self.check_string}."

    def __split_retainer_name(self) -> str:
        try:
            if self.retainer.name.count(",") >= 1:
                short_name = self.retainer.name.split(",", 1)
                short_name = short_name[0].strip()
            elif self.retainer.name.count("-") >= 1:
                short_name = self.retainer.name.split("-", 1)
                short_name = short_name[0].strip()
            else:
                short_name = self.retainer.name
        except (ValueError, IndexError):
            short_name = self.retainer.name

        return short_name


class BaseCheckMaker:
    roll_class = SimpleRoll

    def __init__(self, character, roll_class=None, **kwargs):
        self.character = character
        self.kwargs = kwargs
        if roll_class:
            self.roll_class = roll_class
        self.roll = None

    @classmethod
    def perform_check_for_character(cls, character, **kwargs):
        check = cls(character, **kwargs)
        check.make_check_and_announce()

    def make_check_and_announce(self):
        self.roll = self.roll_class(character=self.character, **self.kwargs)
        self.roll.execute()
        self.announce()

    @property
    def is_success(self):
        return self.roll.is_success

    def announce(self):
        notifier = RoomNotifier(
            self.character,
            room=self.character.location,
            to_player=True,
            to_gm=True,
            to_staff=True,
        )

        notifier.generate()
        notifier.notify(self.roll.roll_message, options={"roll": True})


class PrivateCheckMaker:
    roll_class = SimpleRoll

    def __init__(self, character, receivers, roll_class=None, **kwargs):
        self.character = character
        self.receivers = receivers or []
        self.kwargs = kwargs
        if roll_class:
            self.roll_class = roll_class
        self.roll = None

    @classmethod
    def perform_check_for_character(cls, character, receivers, **kwargs):
        check = cls(character=character, receivers=receivers, **kwargs)
        check.make_check_and_announce()

    def make_check_and_announce(self):
        self.roll = self.roll_class(character=self.character, **self.kwargs)
        self.roll.execute()
        self.announce()

    @property
    def is_success(self) -> bool:
        return self.roll.is_success

    def announce(self):
        """
        Sends a private roll result message to specific players as well as
        to all GMs (player and staff) at that character's location.
        """
        # Notifiers will source nothing if self.character.location is None
        # or if self.receivers is None.
        # They will have empty receiver lists, and thus not do anything.

        # SelfListNotifier will notify the caller if a player or
        # player GM, and notify every player/player-GM on the list.
        player_notifier = SelfListNotifier(
            self.character,
            receivers=self.receivers,
            to_player=True,
            to_gm=True,
        )
        # RoomNotifier will notify every staff member in the room
        staff_notifier = RoomNotifier(
            self.character,
            room=self.character.location,
            to_staff=True,
        )

        # Generate the receivers of the notifications.
        player_notifier.generate()
        staff_notifier.generate()

        # Staff names get highlighted because they're fancy
        staff_names = [f"|c{name}|n" for name in sorted(staff_notifier.receiver_names)]

        # Build list of who is receiving this private roll.  Staff are last
        receiver_names = sorted(player_notifier.receiver_names) + staff_names

        # If only the caller is here to see it, only the caller will be
        # listed for who saw it.
        if receiver_names:
            receiver_suffix = f"(Shared with: {', '.join(receiver_names)})"
        else:
            receiver_suffix = f"(Shared with: {self.character})"

        # Now that we know who is getting it, build the private message string.
        private_msg = f"|w[Private Roll]|n {self.roll.roll_message} {receiver_suffix}"

        # Notify everyone of the roll result.
        player_notifier.notify(private_msg, options={"roll": True})
        staff_notifier.notify(private_msg, options={"roll": True})


class RollResults:
    """Class for ranking the results of rolls, listing ties"""

    tie_threshold = TIE_THRESHOLD

    def __init__(self, rolls):
        self.raw_rolls = sorted(rolls, reverse=True)
        # list of lists of rolls. multiple rolls in a list indicates a tie
        self.results = []

    def rank_results(self):
        for roll in self.raw_rolls:
            is_tie = False
            if self.results:
                last_results = self.results[-1]
                if last_results and last_results[0] == roll:
                    is_tie = True
            if is_tie:
                self.results[-1].append(roll)
            else:
                self.results.append([roll])

    def get_result_string(self):
        result_msgs = []
        for result in self.results:
            if len(result) > 1:
                tie = " ".join(ob.result_message for ob in result)
                result_msgs.append(f"TIE: {tie}")
            else:
                result_msgs.append(result[0].result_message)
        return "\n".join(result_msgs)

    def rank_results_and_get_display(self):
        self.rank_results()
        return self.get_result_string()


class ContestedCheckMaker:
    roll_class = SimpleRoll

    def __init__(self, characters, caller, prefix_string="", roll_class=None, **kwargs):
        self.characters = list(characters)
        self.caller = caller
        self.kwargs = kwargs
        self.prefix_string = prefix_string
        if roll_class:
            self.roll_class = roll_class

    @classmethod
    def perform_contested_check(cls, characters, caller, prefix_string, **kwargs):
        obj = cls(characters, caller, prefix_string, **kwargs)
        obj.perform_contested_check_and_announce()

    def perform_contested_check_and_announce(self):
        rolls = []
        for character in self.characters:
            roll = self.roll_class(character=character, **self.kwargs)
            roll.execute()
            rolls.append(roll)
        results = RollResults(rolls).rank_results_and_get_display()
        roll_message = f"{self.prefix_string}\n{results}"
        self.caller.msg_location_or_contents(roll_message, options={"roll": True})


class OpposingRolls:
    def __init__(self, roll1, roll2, caller, target):
        self.roll1 = roll1
        self.roll2 = roll2
        self.caller = caller
        self.target = target

    def announce(self):
        self.roll1.execute()
        self.roll2.execute()
        rolls = sorted([self.roll1, self.roll2], reverse=True)
        if self.roll1 == self.roll2:
            result = "*** The rolls are |ctied|n. ***"
        else:
            result = f"*** |c{rolls[0].character}|n is the winner. ***"
        msg = f"\n|w*** {self.caller} has called for an opposing check with {self.target}. ***|n\n"
        msg += f"{self.roll1.roll_message}\n{self.roll2.roll_message}\n{result}"
        self.caller.msg_location_or_contents(msg, options={"roll": True})


class DefinedCheckMaker(BaseCheckMaker):
    roll_class = DefinedRoll

    @property
    def outcome(self):
        return self.roll.outcome

    @property
    def value_for_outcome(self):
        return self.outcome.get_value(self.character)
