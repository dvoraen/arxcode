"""
check_utils.py

This module contains the CheckString hierarchy of classes as well as
contains utility functions utilized by the @check code.
"""

from typing import Optional, Tuple, Union

from world.stat_checks.models import DifficultyRating
from world.traits.models import Trait


def get_check_string(stat: str, skill: Optional[str], rating: DifficultyRating) -> str:
    """
    Returns what stat/skill/rating are being checked as a string.
    """
    if skill:
        return f"{stat} and {skill} at {rating}"
    return f"{stat} at {rating}"


def parse_stat_skill(stat_skill_string: str) -> Tuple[str, Optional[str]]:
    """
    Given the Input string, extracts the stat and skill from it.

    Input: <stat> [+ <skill>]
    """
    try:
        stat, skill = stat_skill_string.split("+")
    except ValueError:
        stat = stat_skill_string.strip().lower()
        skill = None
    else:
        stat = stat.strip().lower()
        skill = skill.strip().lower()

    return stat, skill


def extract_value(string: str) -> Tuple[str, int]:
    """
    Given the Input string, extracts name and value.

    Input: name/value
    """
    specify_msg = 'Specify "name/value" for stats and skills.'
    value_msg = "Stat/skill values must be a number."

    try:
        lhs, rhs = string.split("/")
    except ValueError:
        raise CheckStringError(specify_msg) from None

    if not rhs.isdigit():
        raise CheckStringError(value_msg)

    return lhs, int(rhs)


class CheckStringError(Exception):
    pass


class CheckString:
    """
    CheckString is a class that performs data extraction from a
    check string as dictated by the base @check command.

    Input: <stat> [+ <skill>] at <difficulty>
    """

    SYNTAX_MSG = "Usage: stat [+ skill] at <difficulty rating>"
    DIFFICULTY_MSG = "'{rating}' is not a valid difficulty rating."
    STAT_MSG = "{stat} is not a valid stat name."
    SKILL_MSG = "{skill} is not a valid skill name."

    def __init__(self, check_string: str):
        self.check_string = check_string
        self.work_string = check_string

        self.stat: str = None
        self.skill: str = None
        self.rating: DifficultyRating = None

    def __str__(self):
        return self.check_string

    def __repr__(self):
        return f"<CheckString: {self.stat}, {self.skill}, {self.rating}>"

    def parse(self):
        """
        Evaluates the check string and assigns the values contained within
        to the relevant variables (stat, skill, difficulty, etc.).
        """
        self._extract_difficulty()
        self._extract_stat_skill()
        self._validate_stat_skill()

    def _extract_difficulty(self):
        try:
            self.work_string, diff_str = self.work_string.split(" at ")
        except ValueError:
            raise CheckStringError(self.SYNTAX_MSG) from None

        diff_str = diff_str.strip().lower()

        self.rating = DifficultyRating.get_instance_by_name(diff_str)
        if not self.rating:
            raise CheckStringError(self.DIFFICULTY_MSG.format(rating=diff_str))

    def _extract_stat_skill(self):
        self.stat, self.skill = parse_stat_skill(self.work_string)
        self._validate_stat_skill()

    def _validate_stat_skill(self):
        if self.stat not in Trait.get_valid_stat_names():
            raise CheckStringError(self.STAT_MSG.format(stat=self.stat))
        if self.skill and self.skill not in Trait.get_valid_skill_names():
            raise CheckStringError(self.SKILL_MSG.format(skill=self.skill))


class SpoofCheckString(CheckString):
    """
    SpoofCheckString performs data extraction from a check string
    that's supplied by the @gmcheck command.

    It holds the spoof values in addition to the rest.

    Input: <stat>/<stat value> [+ <skill>/<skill value>] at difficulty
    """

    STAT_LIMIT = 20
    SKILL_LIMIT = 20

    SYNTAX_MSG = "Usage: <stat>/<value> [+ <skill>/<value>] at difficulty=<npc name>"
    STAT_LIMIT_MSG = f"Stats must be between 1 and {STAT_LIMIT}."
    SKILL_LIMIT_MSG = f"Skills must be between 1 and {SKILL_LIMIT}."

    def __init__(self, check_string: str):
        super().__init__(check_string)

        self.stat_value = 0
        self.skill_value = 0

    def __repr__(self):
        return f"<SpoofCheckString: {self.stat} {self.stat_value}, {self.skill} {self.skill_value}, {self.rating}>"

    def parse(self):
        self._extract_difficulty()
        self._extract_stat_skill()
        self._validate_stat_skill()
        self.__validate_spoof_values()

    def _extract_stat_skill(self):
        # If syntax error on stat only
        if self.work_string.count("+") == 0 and self.work_string.count("/") != 1:
            raise CheckStringError(self.SYNTAX_MSG)
        # If syntax error on stat+skill
        elif self.work_string.count("+") == 1 and self.work_string.count("/") != 2:
            raise CheckStringError(self.SYNTAX_MSG)

        try:
            stat_string, skill_string = self.work_string.split("+")
        except ValueError:
            stat_string = self.work_string.strip()
            skill_string = None

        # Extract stat and its spoof value
        self.stat, self.stat_value = extract_value(stat_string.strip())
        self.stat = self.stat.strip()

        # Extract skill and its spoof value, if applicable
        if skill_string:
            self.skill, self.skill_value = extract_value(skill_string.strip())
            self.skill = self.skill.strip()

    def __validate_spoof_values(self):
        if self.stat_value < 1 or self.stat_value > self.STAT_LIMIT:
            raise CheckStringError(self.STAT_LIMIT_MSG)
        if self.skill:
            if self.skill_value < 1 or self.skill_value > self.SKILL_LIMIT:
                raise CheckStringError(self.SKILL_LIMIT_MSG)


class RetainerCheckString(CheckString):
    """
    RetainerCheckValues performs data extraction on a check string
    provided by @check/retainer.

    It holds the value of the given retainer_id as well as the rest.

    Input: <id/name>/<stat> [+ <skill>] at difficulty
    """

    SYNTAX_MSG = "Usage: <id/name>/<stat> [+ <skill>] at <difficulty rating>"

    def __init__(self, check_string: str):
        super().__init__(check_string)

        self.retainer_id: Union[str, int] = None

    def __repr__(self):
        return f"<RetainerCheckString: {self.retainer_id}; {self.stat}, {self.skill}, {self.rating}"

    def parse(self):
        self.__extract_retainer_id()
        self._extract_difficulty()
        self._extract_stat_skill()
        self._validate_stat_skill()

    def __extract_retainer_id(self):
        try:
            self.retainer_id, self.work_string = self.work_string.split("/")
        except ValueError:
            raise CheckStringError(self.SYNTAX_MSG) from None


class VsCheckString(CheckString):
    """
    VsCheckString performs data extraction on a check string
    provided by @check/vs.

    It holds both the left side and right side stat/skill values.

    Input: stat [+ skill] vs stat [+ skill]
    """

    SYNTAX_MSG = "Usage: stat [+ skill] vs stat [+ skill]=target"
    TWO_CHECK_MSG = "Must provide two checks."

    def __init__(self, check_string: str):
        super().__init__(check_string)

        self.vs_stat: str = None
        self.vs_skill: str = None

    def __repr__(self):
        return f"<VsCheckString: {self.stat}, {self.skill} vs {self.vs_stat}, {self.vs_skill}>"

    def parse(self):
        self._extract_stat_skill()
        self._validate_stat_skill()

    def _extract_stat_skill(self):
        try:
            lhs, rhs = self.work_string.split(" vs ")
        except ValueError:
            raise CheckStringError(self.TWO_CHECK_MSG) from None

        self.stat, self.skill = parse_stat_skill(lhs)
        self.vs_stat, self.vs_skill = parse_stat_skill(rhs)

    def _validate_stat_skill(self):
        super()._validate_stat_skill()

        if self.vs_stat not in Trait.get_valid_stat_names():
            raise CheckStringError(self.STAT_MSG.format(stat=self.vs_stat))
        if self.vs_skill and self.vs_skill not in Trait.get_valid_skill_names():
            raise CheckStringError(self.SKILL_MSG.format(skill=self.vs_skill))
