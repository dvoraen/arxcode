from typing import Union

from world.stat_checks.models import DifficultyRating
from world.traits.models import Trait


def get_check_string(stat, skill, rating):
    """
    Returns what stat/skill/rating are being checked as a string.
    """
    if skill:
        return f"{stat} and {skill} at {rating}"
    return f"{stat} at {rating}"


class CheckStringError(Exception):
    pass


class CheckString:
    """
    CheckValues is a class that performs data extraction from an Arx
    'check string' as dictated by the @check command.

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
        # Before split: "stat + skill"
        # After split: "stat ", " skill"
        try:
            self.stat, self.skill = self.work_string.split("+")
        except ValueError:
            self.stat = self.work_string.strip().lower()
            # self.skill is None
        else:
            self.stat = self.stat.strip().lower()
            self.skill = self.skill.strip().lower()

        # Validate stat and skill names where applicable.
        if self.stat not in Trait.get_valid_stat_names():
            raise CheckStringError(self.STAT_MSG.format(stat=self.stat))
        if self.skill and self.skill not in Trait.get_valid_skill_names():
            raise CheckStringError(self.SKILL_MSG.format(skill=self.skill))


class SpoofCheckString(CheckString):
    """
    SpoofCheckValues performs additional data extraction from an Arx
    'check string' that's supplied by the @gmcheck command.

    Input: <stat>/<stat value> [+ <skill>/<skill value>] at difficulty
    """

    STAT_LIMIT = 20
    SKILL_LIMIT = 20

    SYNTAX_MSG = "Usage: <stat>/<value> [+ <skill>/<value>] at difficulty=<npc name>"
    SPECIFY_MSG = 'Specify "name/value" for stats and skills.'
    VALUE_MSG = "Stat/skill values must be a number."
    STAT_LIMIT_MSG = f"Stats must be between 1 and {STAT_LIMIT}."
    SKILL_LIMIT_MSG = f"Skills must be between 1 and {SKILL_LIMIT}."

    def __init__(self, check_string: str):
        super().__init__(check_string)

        self.stat_value = 0
        self.skill_value = 0

    def __repr__(self):
        return f"<SpoofCheckString: {self.stat} {self.stat_value}, {self.skill} {self.skill_value}, {self.rating}>"

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
        self.stat, self.stat_value = self.__extract_value(stat_string.strip())
        self.stat = self.stat.strip()

        # Extract skill and its spoof value, if applicable
        if skill_string:
            self.skill, self.skill_value = self.__extract_value(skill_string.strip())
            self.skill = self.skill.strip()

        # Validate stat/skill names.
        if self.stat not in Trait.get_valid_stat_names():
            raise CheckStringError(self.STAT_MSG.format(stat=self.stat))
        if self.skill and self.skill not in Trait.get_valid_skill_names():
            raise CheckStringError(self.SKILL_MSG.format(skill=self.skill))

        # Validate spoof values.
        if self.stat_value < 1 or self.stat_value > self.STAT_LIMIT:
            raise CheckStringError(self.STAT_LIMIT_MSG)
        if self.skill:
            if self.skill_value < 1 or self.skill_value > self.SKILL_LIMIT:
                raise CheckStringError(self.SKILL_LIMIT_MSG)

    def __extract_value(self, string: str):
        try:
            lhs, rhs = string.split("/")
        except ValueError:
            raise CheckStringError(self.SPECIFY_MSG) from None

        if not rhs.isdigit():
            raise CheckStringError(self.VALUE_MSG)

        return lhs, int(rhs)


class RetainerCheckString(CheckString):
    """
    RetainerCheckValues

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

    def __extract_retainer_id(self):
        try:
            self.retainer_id, self.work_string = self.work_string.split("/")
        except ValueError:
            raise CheckStringError(self.SYNTAX_MSG) from None
