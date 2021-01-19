from typing import Union

from commands.base import ArxCommand
from world.stat_checks.models import DifficultyRating, DamageRating
from world.traits.models import Trait
from world.stat_checks.check_maker import (
    BaseCheckMaker,
    PrivateCheckMaker,
    ContestedCheckMaker,
    SimpleRoll,
    SpoofRoll,
    RetainerRoll,
    OpposingRolls,
)
from world.stat_checks.check_utils import (
    get_check_string,
    CheckStringError,
    CheckString,
    SpoofCheckString,
    RetainerCheckString,
    VsCheckString,
)

from world.dominion.models import Agent


class CmdStatCheck(ArxCommand):
    """
    CmdStatCheck is a replacement for the previous CmdDiceCheck command.
    """

    key = "check"
    aliases = ["roll"]
    locks = "cmd:all()"

    def get_help(self, caller, cmdset):
        msg = """
    Usage:
        @check stat + skill at <difficulty rating>[=<player1>,<player2>,etc.]
        @check/contest name1,name2,name3,etc=stat (+ skill) at <rating>
        @check/contest/here stat (+ skill) at <difficulty rating>
        @check/vs stat (+ skill) vs stat(+skill)=<target name>
        @check/retainer <id/name>/<stat> [+ <skill>] at <difficulty rating>
            [=<player1>,<player2>,etc.]

    Normal check is at a difficulty rating. Rating must be one of 
    {difficulty_ratings}.
    
    check/contest allows a GM to have everyone selected to make a check,
    listing the results in order of results. check/contest/here is 
    shorthand to check everyone in a room aside from the GM.
    """
        ratings = ", ".join(str(ob) for ob in DifficultyRating.get_all_instances())
        return msg.format(difficulty_ratings=ratings)

    def func(self):
        try:
            if "contest" in self.switches:
                return self.do_contested_check()
            if "vs" in self.switches:
                return self.do_opposing_checks()
            if "retainer" in self.switches:
                return self.do_retainer_check()
            if self.rhs:
                return self.do_private_check()
            return self.do_normal_check()
        except self.error_class as err:
            self.msg(err)

    def do_normal_check(self):
        try:
            check = CheckString(self.args)
            check.parse()
        except CheckStringError as error:
            raise self.error_class(error) from None

        BaseCheckMaker.perform_check_for_character(
            self.caller, stat=check.stat, skill=check.skill, rating=check.rating
        )

    def do_private_check(self):
        try:
            check = CheckString(self.lhs)
            check.parse()
        except CheckStringError as error:
            raise self.error_class(error) from None

        PrivateCheckMaker.perform_check_for_character(
            self.caller,
            stat=check.stat,
            skill=check.skill,
            rating=check.rating,
            receivers=self.rhslist,
        )

    def do_retainer_check(self):
        try:
            check = RetainerCheckString(self.lhs)
            check.parse()
        except CheckStringError as error:
            raise self.error_class(error) from None

        # Get retainer object
        retainer = self._get_retainer_from_id(check.retainer_id)

        if retainer.dbobj.location != self.caller.location:
            raise self.error_class("Your retainer must be in the room with you.")

        if not self.rhslist:
            BaseCheckMaker.perform_check_for_character(
                character=self.caller,
                receivers=None,
                roll_class=RetainerRoll,
                retainer=retainer,
                stat=check.stat,
                skill=check.skill,
                rating=check.rating,
            )
        else:
            PrivateCheckMaker.perform_check_for_character(
                character=self.caller,
                receivers=self.rhslist,
                roll_class=RetainerRoll,
                retainer=retainer,
                stat=check.stat,
                skill=check.skill,
                rating=check.rating,
            )

    def _get_retainer_from_id(self, retainer_id: Union[str, int]):
        try:
            if retainer_id.isdigit():
                retainer = self.caller.player_ob.retainers.get(id=retainer_id)
            else:
                retainer = self.caller.player_ob.retainers.get(
                    name__icontains=retainer_id
                )
        except Agent.DoesNotExist:
            raise self.error_class("Unable to find retainer by that name/ID.") from None
        except Agent.MultipleObjectsReturned:
            raise self.error_class(
                "Multiple retainers found, be more specific or use ID."
            ) from None

        return retainer

    def do_contested_check(self):
        if not self.caller.check_staff_or_gm():
            raise self.error_class("You are not GMing an event in this room.")

        # Get the characters for this particular check/contest.
        characters = []
        if "here" in self.switches:
            characters = [
                ob
                for ob in self.caller.location.contents
                if ob.is_character and ob != self.caller
            ]
            check_string = self.args
        else:
            if not self.rhs:
                raise self.error_class(
                    "You must specify the names of characters for the contest."
                )
            for name in self.lhslist:
                character = self.search(name)
                if not character:
                    return
                characters.append(character)
            check_string = self.rhs

        try:
            check = CheckString(check_string)
            check.parse()
        except CheckStringError as error:
            raise self.error_class(error) from None

        prefix = f"{self.caller} has called for a check of {get_check_string(check.stat, check.skill, check.rating)}."
        ContestedCheckMaker.perform_contested_check(
            characters,
            self.caller,
            prefix,
            stat=check.stat,
            skill=check.skill,
            rating=check.rating,
        )

    def do_opposing_checks(self):
        if not self.rhs:
            raise self.error_class("You must provide a target.")
        target = self.search(self.rhs)
        if not target:
            return
        if not target.is_character:
            raise self.error_class("That is not a character.")

        try:
            check = VsCheckString(self.lhs)
            check.parse()
        except CheckStringError as error:
            raise self.error_class(error) from None

        # use first difficulty value as the rating both checks share
        rating = DifficultyRating.get_all_cached_instances()[0]

        caller_roll = SimpleRoll(
            character=self.caller, stat=check.stat, skill=check.skill, rating=rating
        )
        vs_roll = SimpleRoll(
            character=target, stat=check.vs_stat, skill=check.vs_skill, rating=rating
        )

        OpposingRolls(caller_roll, vs_roll, self.caller, target).announce()


class CmdHarm(ArxCommand):
    """
    CmdHarm is a new replacement for the older, deprecated harm command.
    """

    key = "harm"
    locks = "cmd:all()"
    help_category = "GMing"

    def get_help(self, caller, cmdset):
        msg = """
        Causes damage to a character during a story

        Usage: harm <character>=<damage rating>[,<damage type>]

        The harm command is used to inflict damage on a character during a
        story, usually as the result of a failed roll. Damage is determined
        by the rating of the damage you select.

        Ratings: {damage_ratings}
        """
        ratings = ", ".join(str(ob) for ob in DamageRating.get_all_instances())
        return msg.format(damage_ratings=ratings)

    def func(self):
        try:
            return self.do_harm()
        except self.error_class as err:
            self.msg(err)

    def do_harm(self):
        damage = ""
        target = self.caller.search(self.lhs)
        if not target:
            return
        if self.rhslist:
            damage = DamageRating.get_instance_by_name(self.rhslist[0])
        if not damage:
            raise self.error_class("No damage rating found by that name.")
        if target != self.caller and not self.caller.check_staff_or_gm():
            raise self.error_class("You may only harm others if GMing an event.")
        self.msg(f"Inflicting {damage} on {target}.")
        damage.do_damage(target)


class CmdSpoofCheck(ArxCommand):

    key = "@gmcheck"
    locks = "cmd:all()"

    STAT_LIMIT = 20
    SKILL_LIMIT = 20

    def get_help(self, caller, cmdset):
        ratings = ", ".join(str(obj) for obj in DifficultyRating.get_all_instances())
        msg = f"""
    @gmcheck

    Usage:
        @gmcheck <stat>/<value> [+ <skill>/<value>] at <difficulty>[=<npc name>]
        @gmcheck/crit <same as above>
        @gmcheck/flub <same as above>

    Performs a stat + skill at difficulty check with specified values.  Intended
    for GMs to make rolls for NPCs that don't necessarily exist as characters
    in-game.
    
    The /crit switch allows the roll to crit or botch.
    The /flub switch intentionally fails the roll.

    NPC name allows for a GM to optionally assign an NPC name to their roll.

    Difficulty ratings are as follows: {ratings}
    """
        return msg

    def func(self):
        try:
            self.do_spoof_roll()
        except self.error_class as err:
            self.msg(err)

    def do_spoof_roll(self):
        try:
            check = SpoofCheckString(self.lhs if self.rhs else self.args)
            check.parse()
        except CheckStringError as error:
            raise self.error_class(error)

        # Will be None if not self.rhs, which is what we want.
        npc_name = self.rhs

        can_crit = "crit" in self.switches
        is_flub = "flub" in self.switches

        BaseCheckMaker.perform_check_for_character(
            self.caller,
            roll_class=SpoofRoll,
            stat=check.stat,
            stat_value=check.stat_value,
            skill=check.skill,
            skill_value=check.skill_value,
            rating=check.rating,
            npc_name=npc_name,
            can_crit=can_crit,
            is_flub=is_flub,
        )

    def _extract_difficulty(self, args: str, syntax: str) -> (str, DifficultyRating):
        try:
            lhs, rhs, *remainder = args.split(" at ")
        except ValueError:
            raise self.error_class(syntax)
        else:
            if remainder:
                raise self.error_class(syntax)

        rhs = rhs.strip().lower()
        difficulty = DifficultyRating.get_instance_by_name(rhs)
        if not difficulty:
            raise self.error_class(f"{rhs} is not a valid difficulty rating.")

        return lhs, difficulty

    def _extract_stat_skill_string(self, args: str, syntax: str) -> (str, str):
        # If syntax error on stat only
        if args.count("+") == 0 and args.count("/") != 1:
            raise self.error_class(syntax)
        # If syntax error on stat+skill
        elif args.count("+") == 1 and args.count("/") != 2:
            raise self.error_class(syntax)

        try:
            stat_str, skill_str, *remainder = args.split("+")
        except ValueError:
            stat_str = args
            skill_str = None
        else:
            if remainder:
                raise self.error_class(syntax)

        stat_str = stat_str.strip().lower()
        if skill_str:
            skill_str = skill_str.strip().lower()

        return stat_str, skill_str

    def _get_values(self, args: str) -> (str, int):
        try:
            lhs, rhs = args.split("/")
        except ValueError:
            raise self.error_class('Specify "name/value" for stats and skills.')

        if not rhs.isdigit():
            raise self.error_class("Stat/skill values must be a number.")

        return lhs, int(rhs)
