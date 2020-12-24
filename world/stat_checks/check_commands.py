from commands.base import ArxCommand
from world.stat_checks.models import DifficultyRating, DamageRating
from world.traits.models import Trait
from world.stat_checks.check_maker import (
    BaseCheckMaker,
    PrivateCheckMaker,
    GroupCheckMaker,
    ContestedCheckMaker,
    SimpleRoll,
    OpposingRolls,
)


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
        @check/with stat [+ skill]=<player1>,<player2>,<player3>,etc.
    
    Normal check is at a difficulty rating. Rating must be one of 
    {difficulty_ratings}.
    
    check/contest allows a GM to have everyone selected to make a check,
    listing the results in order of results. check/contest/here is 
    shorthand to check everyone in a room aside from the GM.

    check/with is a collaborative roll for a given check.  The user of
    the command and each specific player will all contribute towards a
    single result, which measures how well the players did at the task.
    """
        ratings = ", ".join(str(ob) for ob in DifficultyRating.get_all_instances())
        return msg.format(difficulty_ratings=ratings)

    def func(self):
        try:
            if "contest" in self.switches:
                return self.do_contested_check()
            if "vs" in self.switches:
                return self.do_opposing_checks()
            if "with" in self.switches:
                return self.do_group_check()
            if self.rhs:
                return self.do_private_check()
            return self.do_normal_check()
        except self.error_class as err:
            self.msg(err)

    def do_normal_check(self):
        stat, skill, rating = self.get_check_values_from_args(
            self.args, "Usage: stat [+ skill] at <difficulty rating>"
        )
        BaseCheckMaker.perform_check_for_character(
            self.caller, stat=stat, skill=skill, rating=rating
        )

    def do_private_check(self):
        receiver_list = []
        for name in self.rhslist:
            receiver = self.caller.search(name.strip(), use_nicks=True)
            if receiver:
                receiver_list.append(receiver)

        stat, skill, rating = self.get_check_values_from_args(
            self.lhs,
            "Usage: stat [+ skill] at <difficulty rating>[=<player1>,<player2>,etc.]",
        )
        PrivateCheckMaker.perform_check_for_character(
            self.caller, stat=stat, skill=skill, rating=rating, receivers=receiver_list
        )

    def do_group_check(self):
        # Gotta have helpers to use this command.
        if not self.rhslist:
            raise self.error_class(
                "@check/with: You must specify who is assisting you."
            )

        # Make the helper list.
        helper_list = []
        for name in self.rhslist:
            helper = self.caller.search(name.strip(), use_nicks=True)
            if helper:
                helper_list.append(helper)

        # Can't include yourself as a helper; you already are helping!
        if self.caller in helper_list:
            raise self.error_class(
                "@check/with: Exclude yourself; specify only other characters as helpers."
            )

        # Get stat, skill from self.lhs
        stat, skill = self.get_stat_and_skill_from_args(self.lhs)

        # Private roll argument exists for future upgrade.
        # See GroupCheckMaker.announce() in check_maker.py for details
        # of how I envision that.
        GroupCheckMaker.perform_check_for_characters(
            self.caller,
            stat=stat,
            skill=skill,
            helpers=set(helper_list),
            private_roll=False,
        )

    def get_check_values_from_args(self, args, syntax):
        try:
            stats_string, rating_string = args.split(" at ")
        except (TypeError, ValueError):
            raise self.error_class(syntax)
        stat, skill = self.get_stat_and_skill_from_args(stats_string)
        rating_string = rating_string.strip()
        rating = DifficultyRating.get_instance_by_name(rating_string)
        if not rating:
            raise self.error_class(
                f"'{rating_string}' is not a valid difficulty rating."
            )
        return stat, skill, rating

    def get_stat_and_skill_from_args(self, stats_string):
        skill = None
        try:
            stat, skill = stats_string.split("+")
            stat = stat.strip().lower()
            skill = skill.strip().lower()
        except (TypeError, ValueError):
            stat = stats_string.strip().lower()
        if stat not in Trait.get_valid_stat_names():
            raise self.error_class(f"{stat} is not a valid stat name.")
        if skill and skill not in Trait.get_valid_skill_names():
            raise self.error_class(f"{skill} is not a valid skill name.")
        return stat, skill

    def do_contested_check(self):
        if not self.caller.check_staff_or_gm():
            raise self.error_class("You are not GMing an event in this room.")
        characters = []
        if "here" in self.switches:
            characters = [
                ob
                for ob in self.caller.location.contents
                if ob.is_character and ob != self.caller
            ]
            stat, skill, rating = self.get_check_values_from_args(
                self.args, "Usage: stat [+ skill] at <difficulty rating>"
            )
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
            stat, skill, rating = self.get_check_values_from_args(
                self.rhs, "Usage: stat [+ skill] at <difficulty rating>"
            )
        prefix = f"{self.caller} has called for a check of {SimpleRoll.get_check_string(stat, skill, rating)}."
        ContestedCheckMaker.perform_contested_check(
            characters, self.caller, prefix, stat=stat, skill=skill, rating=rating
        )

    def do_opposing_checks(self):
        if not self.rhs:
            raise self.error_class("You must provide a target.")
        target = self.search(self.rhs)
        if not target:
            return
        if not target.is_character:
            raise self.error_class("That is not a character.")
        check_strings = self.lhs.split(" vs ")
        if len(check_strings) != 2:
            raise self.error_class("Must provide two checks.")
        args = [(self.caller, check_strings[0]), (target, check_strings[1])]
        # use first difficulty value as the rating both checks share
        rating = DifficultyRating.get_all_cached_instances()[0]
        rolls = []
        for arg in args:
            stat, skill = self.get_stat_and_skill_from_args(arg[1])
            rolls.append(
                SimpleRoll(character=arg[0], stat=stat, skill=skill, rating=rating)
            )
        OpposingRolls(rolls[0], rolls[1], self.caller, target).announce()


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
        target = self.caller.search(self.lhs)
        if not target:
            return
        damage = DamageRating.get_instance_by_name(self.rhs or "")
        if not damage:
            raise self.error_class("No damage rating found by that name.")
        if target != self.caller and not self.caller.check_staff_or_gm():
            raise self.error_class("You may only harm others if GMing an event.")
        self.msg(f"Inflicting {damage} on {target}.")
        damage.do_damage(target)
