from random import randint
from functools import total_ordering

from world.conditions.modifiers_handlers import ModifierHandler
from world.stat_checks.models import (
    DifficultyRating,
    RollResult,
    StatWeight,
    NaturalRollType,
    StatCheck,
)

# I need type hints like a crutch.
from typing import List


TIE_THRESHOLD = 5


def check_rolls_tied(roll1, roll2, tie_value=TIE_THRESHOLD):
    if roll1.roll_result_object != roll2.roll_result_object:
        return False
    return abs(roll1.result_value - roll2.result_value) < tie_value


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
    # - The raw rolls of each player
    # - The thresholds for each stage of success.
    # - Comparisons to those thresholds.

    # What to research:
    # - ModifierHandler
    # - Database (models for group check thresholds)
    #    * model for group check thresholds
    #    * jinja2 templates needed for the result strings
    #       ^ result rolls (DISASTER, LEGENDARY!!1!)
    #       ? noteworthy rolls ("contributed greatly!")

    def execute(self):
        pass

    def build_result_strings(self) -> List[str]:
        msgs = [
            f"|w*** |c{self.character} |whas called for a group check of |n{check_string}|w. ***|n",
            f"|wParticipating: |n{self.character}, {', '.join(sorted(self.helpers))}",
        ]
        return msgs

    @staticmethod
    def get_stat_skill_string(stat, skill):
        if skill:
            return f"{stat} and {skill}"
        return f"{stat}"


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

    def __init__(self, character, roll_class=None, **kwargs):
        self.character = character
        self.room = character and character.location
        self.kwargs = kwargs
        self.roll: GroupRoll = None
        self.stat: str = self.kwargs.get("stat")
        self.skill: str = self.kwargs.get("skill", None)
        self.helpers: list = self.kwargs.get("helpers", [])
        self.private_roll: bool = self.kwargs.get("private_roll", False)
        if roll_class:
            self.roll_class = roll_class

    @classmethod
    def perform_check_for_character(cls, character, **kwargs):
        check = cls(character, **kwargs)
        check.make_check()
        check.announce()

    def make_check(self):
        if not self.roll:
            self.roll = self.roll_class(character=self.character, **self.kwargs)
        self.roll.execute()

    def announce(self):
        msgs = self.roll.build_result_strings()

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

        # Send to caller.
        for msg in msg_list:
            self.character.msg(msg, options={"roll": True})

        # Send to assistants.
        for player in player_list:
            for msg in msg_list:
                player.msg(msg, options={"roll": True})

    def announce_to_player_gms(self, msg_list: List[str]):
        """ Sends the contents of msg_list to any PC GMs in the room. """
        gm_list = []

        for pc_gm in gm_list:
            for msg in msg_list:
                pc_gm.msg(msg, options={"roll": True})

    def announce_to_staff(self, msg_list: List[str]):
        """ Sends the contents of msg_list to any Staff GMs in the room. """
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
