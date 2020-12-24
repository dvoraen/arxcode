from random import randint
from functools import total_ordering

from typing import List, Dict

from world.conditions.modifiers_handlers import ModifierHandler
from world.stat_checks.models import (
    DifficultyRating,
    GroupDifficultyRating,
    RollResult,
    GroupRollResult,
    StatWeight,
    NaturalRollType,
    StatCheck,
)

TIE_THRESHOLD = 5


def check_rolls_tied(roll1, roll2, tie_value=TIE_THRESHOLD):
    if roll1.roll_result_object != roll2.roll_result_object:
        return False
    return abs(roll1.result_value - roll2.result_value) < tie_value


class RawRoll:
    """
    A RawRoll is a die roll of a given stat (and skill if applicable)
    that is modified only by a knack for it, and if it's a crit or
    a botch.
    """

    def __init__(self, character, stat: str = None, skill: str = None):
        self.character = character
        self.stat = stat
        self.skill = skill
        self.raw_roll = 0
        self.full_roll = 0
        self.natural_roll_type: NaturalRollType = None

    def __lt__(self, rhs: "RawRoll") -> bool:
        return self.full_roll < rhs.full_roll

    def __le__(self, rhs: "RawRoll") -> bool:
        return self.full_roll <= rhs.full_roll

    def __gt__(self, rhs: "RawRoll") -> bool:
        return self.full_roll > rhs.full_roll

    def __ge__(self, rhs: "RawRoll") -> bool:
        return self.full_roll >= rhs.full_roll

    def __eq__(self, rhs: "RawRoll") -> bool:
        return self.full_roll == rhs.full_roll

    def execute(self):
        self.raw_roll = randint(1, 100)
        self.full_roll = self.raw_roll
        self.full_roll += self.get_stat_roll_value()
        self.full_roll += self.get_skill_roll_value()
        self.full_roll += self.get_knack_roll_value()

        # Was it a crit, botch, or neither?
        self.natural_roll_type = NaturalRollType.get_roll_type(self.raw_roll)

    def get_stat_roll_value(self) -> int:
        if not self.stat:
            return 0

        base = self.character.traits.get_stat_value(self.stat)
        only_stat = not self.skill
        return StatWeight.get_weighted_value_for_stat(base, only_stat)

    def get_skill_roll_value(self) -> int:
        if not self.skill:
            return 0

        base = self.character.traits.get_skill_value(self.skill)
        return StatWeight.get_weighted_value_for_skill(base)

    def get_knack_roll_value(self) -> int:
        try:
            mods: ModifierHandler = self.character.mods
            base = mods.get_total_roll_modifiers([self.stat], [self.skill])
        except AttributeError:
            return 0
        return StatWeight.get_weighted_value_for_knack(base)

    # Reminder to self: this is for jinja2 templates
    def get_context(self) -> dict:
        crit = None
        botch = None
        if self.natural_roll_type:
            if self.natural_roll_type.is_crit:
                crit = self.natural_roll_type
            else:
                botch = self.natural_roll_type

        return {
            "character": self.character,
            "value": self.full_roll,
            "crit": crit,
            "botch": botch,
        }


@total_ordering
class SimpleRoll:
    def __init__(
        self,
        character=None,
        stat=None,
        skill=None,
        rating: DifficultyRating = None,
        receivers: list = None,
        tie_threshold: int = TIE_THRESHOLD,
        **kwargs,
    ):
        self.character = character
        self.receivers = receivers or []
        self.stat = stat
        self.skill = skill
        self.result_value = None
        self.result_message = None
        self.room = character and character.location
        self.rating = rating
        self.raw_roll = None
        self.roll_result_object = None
        self.natural_roll_type = None
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

    def get_roll_value_for_rating(self):
        return self.rating.value

    def execute(self):
        """Does the actual roll"""
        self.raw_roll = randint(1, 100)
        val = self.get_roll_value_for_traits()
        val += self.get_roll_value_for_knack()
        val -= self.get_roll_value_for_rating()
        val += self.raw_roll
        self.result_value = val
        # we use our raw roll and modified toll to determine if our roll is special
        self.natural_roll_type = self.check_for_crit_or_botch()
        self.roll_result_object = RollResult.get_instance_for_roll(
            val, natural_roll_type=self.natural_roll_type
        )
        self.result_message = self.roll_result_object.render(**self.get_context())

    @property
    def is_success(self):
        return self.roll_result_object.is_success

    def get_roll_value_for_traits(self):
        val = self.get_roll_value_for_stat()
        val += self.get_roll_value_for_skill()
        return val

    def get_context(self) -> dict:
        crit = None
        botch = None
        if self.natural_roll_type:
            if self.natural_roll_type.is_crit:
                crit = self.natural_roll_type
            else:
                botch = self.natural_roll_type
        return {
            "character": self.character,
            "roll": self.result_value,
            "result": self.roll_result_object,
            "natural_roll_type": self.natural_roll_type,
            "crit": crit,
            "botch": botch,
        }

    @classmethod
    def get_check_string(cls, stat, skill, rating):
        roll_message = f"{stat} "
        if skill:
            roll_message += f"and {skill} "
        roll_message += f"at {rating}"
        return roll_message

    @property
    def roll_prefix(self):
        roll_message = f"{self.character} checks {self.get_check_string(self.stat, self.skill, self.rating)}"
        return roll_message

    @property
    def roll_message(self):
        return f"{self.roll_prefix}. {self.result_message}"

    def announce_to_room(self):
        self.character.msg_location_or_contents(
            self.roll_message, options={"roll": True}
        )

    def announce_to_players(self):
        """
        Sends a private roll result message to specific players as well as
        all staff at self.character's location.
        """
        self_list = (
            "me",
            "self",
            str(self.character).lower(),
            str(self.character.key).lower(),
        )

        # Build the list of who is seeing the roll, and the lists of names
        # for the msg of who is seeing the roll.  Staff names are highlighted
        # and last in the lists to draw attention to the fact it was successfully
        # shared with a GM.  The names are also sorted because my left brain
        # insisted that it's more organized this way.
        receiver_list = [
            ob for ob in set(self.receivers) if ob.name.lower() not in self_list
        ]
        staff_receiver_names = [
            "|c%s|n" % ob.name
            for ob in set(self.receivers)
            if ob.check_permstring("Builders")
        ]
        pc_receiver_names = [
            ob.name for ob in set(self.receivers) if not ob.check_permstring("Builders")
        ]

        all_receiver_names = sorted(pc_receiver_names) + sorted(staff_receiver_names)

        # Am I the only (non-staff) recipient?
        if len(receiver_list) == 0:
            receiver_suffix = "(Shared with: self-only)"
        else:
            receiver_suffix = "(Shared with: %s)" % ", ".join(all_receiver_names)

        # Now that we know who is getting it, build the private message string.
        private_msg = f"|w[Private Roll]|n {self.roll_message} {receiver_suffix}"

        # Always sent to yourself.
        self.character.msg(private_msg, options={"roll": True})

        # If caller doesn't have a location, we're done; there's no one
        # else to hear it!
        if not self.character.location:
            return

        # Otherwise, send result to all staff in location.
        staff_list = [
            gm
            for gm in self.character.location.contents
            if gm.check_permstring("Builders")
        ]
        for staff in staff_list:
            # If this GM is the caller or a private receiver, skip them.
            # They were or will be notified.
            if staff == self.character or staff in receiver_list:
                continue
            staff.msg(private_msg, options={"roll": True})

        # Send result message to receiver list, if any.
        for receiver in receiver_list:
            receiver.msg(private_msg, options={"roll": True})

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


class DefinedRoll(SimpleRoll):
    """
    Roll for a pre-created check that's saved in the database, which will be used
    to populate the values for the roll.
    """

    def __init__(self, character, check: StatCheck = None, **kwargs):
        super().__init__(character, **kwargs)
        self.check = check

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
        self.rating = self.check.get_difficulty_rating(
            self.character, **self.roll_kwargs
        )
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
        roll_message = f"{self.character} checks '{self.check}' at {self.rating}"
        return roll_message


class GroupRoll:
    # What we need:
    # - All the players involved in the roll, incl. caller
    # - Access to player traits and knacks.
    # - The raw rolls of each player; generated by execute()
    # - The thresholds for each stage of success.
    # - Comparisons to those thresholds.

    # What to research:
    # - ModifierHandler
    # - Database (models for group check thresholds)
    #    * model for group check thresholds
    #    * jinja2 templates needed for the result strings
    #       ^ result rolls (DISASTER, LEGENDARY!!1!)
    #       ? noteworthy rolls ("contributed greatly!")

    def __init__(self, character, stat: str, skill: str, helpers: list = [], **kwargs):
        self.character = character
        self.stat = stat
        self.skill = skill
        self.helpers = helpers
        self.raw_rolls: List[RawRoll] = []
        self.roll_results: list = []
        self.result_msgs: List[str] = []
        self.kwargs = kwargs

    def execute(self):
        # For character and each helper, generate a RawRoll.
        # Each RawRoll will feed a GroupRollResult into being.
        # The totals of the RawRolls feed a GroupDifficultyRating into being.
        self._generate_raw_rolls()
        # self._generate_group_roll_result()
        self._generate_player_messages()
        self._build_result_message()

    def _generate_raw_rolls(self):
        # Generate raw roll for caller.
        caller_roll = RawRoll(self.character, self.stat, self.skill)
        caller_roll.execute()
        self.raw_rolls.append(caller_roll)

        # Generate raw rolls for helpers.
        for char in self.helpers:
            roll = RawRoll(char, self.stat, self.skill)
            roll.execute()
            self.raw_rolls.append(roll)

    def _generate_group_roll_result(self):
        """
        Determines which difficulty the group succeeded at, based on each
        of the totals of their individual rolls.
        """
        # Add up the raw rolls.
        raw_total = sum([roll.full_roll for roll in self.raw_rolls])

        # Find closest GroupDifficultyRating and set it as the result.
        diff_instances = GroupDifficultyRating.get_all_instances()

    def _generate_player_messages(self):
        """
        Generates the string messages for each RawRoll compared to the
        group's overall success.  (If someone did well or poorly.)
        """
        for roll in self.raw_rolls:
            result = f"{roll.character} contributed! ({roll.full_roll})"
            self.roll_results.append(result)

    def _build_result_message(self):
        helper_names = []
        for helper in self.helpers:
            helper_names.append(str(helper))

        self.result_msgs = [
            f"|w*** |c{self.character} |wleads a group check of {self.stat_skill_string}. ***|n",
            f"|wParticipating: |n{self.character}, {', '.join(sorted(helper_names))}",
        ]
        # self.rolls should be sorted by the roll's final value
        for msg in self.roll_results:
            self.result_msgs.append(msg)

    @property
    def stat_skill_string(self) -> str:
        if self.skill:
            return f"{self.stat} and {self.skill}"
        return f"{self.stat}"

    @property
    def result_messages(self) -> List[str]:
        return self.result_msgs

    def get_group_roll_context(self) -> dict:
        """
        Returns the jinja2 context dict for the group roll itself.
        This is for the templates that say what the final result
        is.
        """
        return {}


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
        self.roll.announce_to_room()

    @property
    def is_success(self):
        return self.roll.is_success


class PrivateCheckMaker:
    roll_class = SimpleRoll

    def __init__(self, character, roll_class=None, **kwargs):
        self.character = character
        self.kwargs = kwargs
        if roll_class:
            self.roll_class = roll_class

    @classmethod
    def perform_check_for_character(cls, character, **kwargs):
        check = cls(character, **kwargs)
        check.make_check_and_announce()

    def make_check_and_announce(self):
        roll = self.roll_class(character=self.character, **self.kwargs)
        roll.execute()
        roll.announce_to_players()


class GroupCheckMaker:
    roll_class = GroupRoll

    def __init__(
        self,
        character,
        helpers: set,
        private_roll: bool = False,
        roll_class=None,
        **kwargs,
    ):
        self.character = character
        self.helpers = helpers
        self.private_roll = private_roll
        self.kwargs = kwargs

        self.room = character and character.location
        self.roll = None
        if roll_class:
            self.roll_class = roll_class

    @classmethod
    def perform_check_for_characters(cls, character, **kwargs):
        check = cls(character, **kwargs)
        check.make_check()
        check.announce()

    def make_check(self):
        self.roll = self.roll_class(
            character=self.character, helpers=self.helpers, **self.kwargs
        )
        self.roll.execute()

    def announce(self):
        msgs = self.roll.result_messages

        if not self.private_roll:
            self.announce_to_room(msgs)
        else:
            self.announce_to_players(msgs, self.helpers)
            self.announce_to_player_gms(msgs)
            self.announce_to_staff(msgs)

    def announce_to_room(self, msg_list: List[str]):
        for msg in msg_list:
            self.character.msg_location_or_contents(msg, options={"roll": True})

    def announce_to_players(self, msg_list: List[str], player_list: list):
        """
        Sends the contents of msg_list to each player on player_list
        and this command's caller.
        """

        # Send to all involved players.
        for player in player_list:
            # Player and Staff GMs will always receive private group rolls,
            # so skip them even if they're involved in the roll.  They don't
            # need to get it multiple times.
            if player.check_staff_or_gm():
                continue
            for msg in msg_list:
                player.msg(msg, options={"roll": True})

    def announce_to_player_gms(self, msg_list: List[str]):
        """ Sends the contents of msg_list to any PC GMs in the room. """
        self.character.msg("announce_to_player_gms() called")
        gm_list = []

        for pc_gm in gm_list:
            for msg in msg_list:
                pc_gm.msg(msg, options={"roll": True})

    def announce_to_staff(self, msg_list: List[str]):
        """ Sends the contents of msg_list to any Staff GMs in the room. """
        self.character.msg("announce_to_staff() called")
        staff_list = []

        # Send to those staff.
        for staff in staff_list:
            for msg in msg_list:
                staff.msg(msg, options={"roll": True})


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
