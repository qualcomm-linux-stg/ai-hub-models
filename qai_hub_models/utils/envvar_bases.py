# ---------------------------------------------------------------------
# Copyright (c) 2025 Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------

from __future__ import annotations

import argparse
import os
from datetime import datetime
from enum import Enum
from functools import partial
from pathlib import Path
from typing import Generic, TypeVar, Union

ParsedT = TypeVar("ParsedT")


class QAIHMEnvvar(Generic[ParsedT]):
    """Class for defining environment variables used in the QAIHM package."""

    # Environment variable name.
    VARNAME: str

    # Argnames (eg. --input_1, -i1) that will represent this envvar,
    # if added as an argparse argument to a script.
    #
    # The first argname is used as the mapping in the parsed namespace.
    # Eg. if the first name is --test-arg, then you access the arg value
    # like so: parser.parse_args().test_arg
    CLI_ARGNAMES: list[str]

    # Message for this envvar to be displayed by an argparse parser's help message.
    CLI_HELP_MESSAGE: str

    @classmethod
    def get(cls, default: ParsedT | None = None) -> ParsedT:
        """
        Get the value of this environment variable.
        If the envvar is unset, returns the default value.
        If the default value is none, returns cls.default()
        """
        envvar = os.environ.get(cls.VARNAME)
        if envvar is not None:
            return cls.parse(envvar)
        if default is None:
            default = cls.default()
        return default

    @classmethod
    def set(cls, value: ParsedT | str | None):
        """
        Set the value of this envvar.
        If value is type ParsedT, it will be serialized to string first.
        If value is None, the envvar will be deleted.
        """
        if value is None:
            if cls.VARNAME in os.environ:
                del os.environ[cls.VARNAME]
        else:
            os.environ[cls.VARNAME] = (
                value if isinstance(value, str) else cls.serialize(value)
            )

    @classmethod
    def patchenv(cls, monkeypatch, value: ParsedT | str | None):
        """
        Patch the value of this envvar for the direction of this test,
        using the provided monkeypatch pytest fixture.

        If value is type ParsedT, it will be serialized to string first.
        If value is None, the envvar will be deleted.
        """
        if value is None:
            if cls.VARNAME in os.environ:
                monkeypatch.delenv(cls.VARNAME)
        elif isinstance(value, str):
            monkeypatch.setenv(cls.VARNAME, value)
        else:
            monkeypatch.setenv(cls.VARNAME, cls.serialize(value))

    @classmethod
    def default(cls) -> ParsedT:
        raise NotImplementedError()

    @classmethod
    def is_default(cls, value: ParsedT | None = None) -> bool:
        """
        Returns whether the given value is the default.

        If value is None, returns whether the current value of this envvar is the default.
        """
        return (value or cls.get()) == cls.default()

    @classmethod
    def parse(cls, value: str) -> ParsedT:
        """Parse the string envvar value."""
        raise NotImplementedError()

    @classmethod
    def serialize(cls, value: ParsedT) -> str:
        """Serialize the parsed envvar value to string."""
        raise NotImplementedError()

    class ParseAction(argparse.Action):
        """Makes sure that the ar"""

        def __init__(
            self,
            option_strings,
            dest,
            envvar: type[QAIHMEnvvar[ParsedT]],
            setenv: bool,
            **kwargs,
        ):
            super().__init__(option_strings, dest, **kwargs)
            self.envvar = envvar
            self.setenv = setenv

        def __call__(self, parser, namespace, values, option_string=None):
            assert isinstance(values, str)
            if self.setenv:
                self.envvar.set(values)
            setattr(namespace, self.dest, self.envvar.parse(values))

    @classmethod
    def add_arg(
        cls,
        parser: argparse.ArgumentParser | argparse._ArgumentGroup,
        default: ParsedT | None = None,
        setenv: bool = False,
    ):
        """
        Adds an argument to the given parser or arg group for this envvar.

        Parameters
        ----------
            parser:
                Argument parser or group.

            default:
                The default for the argument will be the value of the envvar.
                If the envvar is unset, the default for the argument will be the this value.
                If the envvar is unset and this value is None, the default will be cls.default()

            setenv:
                If true, the argument parser will set this environment variable with passed-in CLI value.

        Discussion:
            See cls.CLI_ARGNAMES and cls.CLI_HELP_MESSAGE for more details.

            Note: Argparse will parse the envvar for you to ParsedT. For example,
            if I define QAIHMEnvvar[MyClass], then parser.parse_args().myclass would
            result in a parsed MyClass object, not a string.
        """
        parser.add_argument(
            *cls.CLI_ARGNAMES,
            action=partial(cls.ParseAction, envvar=cls, setenv=setenv),  # type: ignore[arg-type]
            default=cls.get(default),
            help=cls.CLI_HELP_MESSAGE,
        )


class QAIHMBoolEnvvar(QAIHMEnvvar[bool]):
    """
    Boolean environment variable.

    If the envvar is set to any value in TRUTHY_BOOLEAN_VALUES, it will be considered True.

    For example:
        Envvar value of "true" -> parsed to True
        Envvar value of "1" -> parsed to True
        Envvar value of "false" -> parsed to False
        Envvar value of "asdf" -> parsed to False
    """

    TRUTHY_BOOLEAN_VALUES = {"true", "1", "on", "yes"}

    @classmethod
    def parse(cls, value: str) -> bool:
        return value.lower() in QAIHMBoolEnvvar.TRUTHY_BOOLEAN_VALUES

    @classmethod
    def serialize(cls, value: bool) -> str:
        return "1" if value else "0"

    class StoreTrueFalseAction(argparse._StoreConstAction):
        def __init__(
            self,
            option_strings,
            dest,
            const: bool,
            envvar: type[QAIHMEnvvar[ParsedT]],
            setenv: bool,
            **kwargs,
        ):
            super().__init__(option_strings, dest, const, **kwargs)
            self.envvar = envvar
            self.setenv = setenv

        def __call__(self, parser, namespace, values, option_string=None):
            super().__call__(parser, namespace, values, option_string)
            if self.setenv:
                self.envvar.set(self.const)

    @classmethod
    def add_arg(
        cls,
        parser: argparse.ArgumentParser,
        default: bool | None = None,
        setenv: bool = False,
    ):
        """
        Adds an argument to the given parser or arg group for this envvar.

        CLI arguments are passed with no value to flip the boolean.
        For example:
            Say we have a bool envvar with CLI_ARGS = ['--set-bool].
            If param 'default' is false:
                `parser.parse_args([]).set_bool == false`
                `parser.parse_args([`--set-bool`]).set_bool == true`
            If param 'default' is true:
                `parser.parse_args([]).set_bool == true`
                `parser.parse_args([`--set-bool`]).set_bool == false`

        If the current envvar is set to the opposite of param 'default', then
        `--no-` will be added to the beginning of the argname.
        For example:
            Say we have a bool envvar with CLI_ARGS = ['--set-bool].
            If param 'default' is false, but os.environ[cls.VARNAME] == True
                `parser.parse_args([]).set_bool == false`
                `parser.parse_args([`--no-set-bool`]).set_bool == true`
            If param 'default' is true, but os.environ[cls.VARNAME] == False
                `parser.parse_args([]).set_bool == true`
                `parser.parse_args([`--no-set-bool`]).set_bool == false`
        """
        default = cls.default() if default is None else default
        if cls.VARNAME in os.environ and cls.get(default) != default:
            args: list[str] = []
            for x in cls.CLI_ARGNAMES:
                if x.startswith("--"):
                    x = "--no-" + x[2:]
                elif x.startswith("-"):
                    x = "-no-" + x[1:]
                args.append(x)
            dest = cls.CLI_ARGNAMES[0]
            if dest.startswith("--"):
                dest = dest[2:]
            elif dest.startswith("-"):
                dest = dest[1:]
            dest = dest.replace("-", "_")
        else:
            args = cls.CLI_ARGNAMES
            dest = None

        parser.add_argument(
            *args,
            action=partial(
                cls.StoreTrueFalseAction,
                const=not cls.get(default),
                envvar=cls,
                setenv=setenv,
            ),  # type: ignore[arg-type]
            default=cls.get(default),
            dest=dest,
            help=cls.CLI_HELP_MESSAGE,
        )


class QAIHMStringEnvvar(QAIHMEnvvar[str]):
    """String (unparsed) environment variable."""

    @classmethod
    def parse(cls, value: str) -> str:
        return value

    @classmethod
    def serialize(cls, value: str) -> str:
        return value


class QAIHMStringListEnvvar(QAIHMEnvvar[list[str]]):
    """
    Comma-separated string list environment variable.

    Example:
        Envvar value of "a , b,c,d" -> parsed to ['a','b','c','d']
    """

    @classmethod
    def parse(cls, value: str) -> list[str]:
        return [x.strip() for x in value.lower().split(",")]

    @classmethod
    def serialize(cls, value: list[str]) -> str:
        return ",".join(value)


EnumT = TypeVar("EnumT", bound=Enum)


class QAIHMStrSetWithEnumEnvvar(QAIHMEnvvar[set[Union[str, EnumT]]], Generic[EnumT]):
    """
    Comma separated string set environment variable.

    The set may contain enum values. Any string that matches the value of
    an enum element will be parsed to that enum.

    Example:
        class MyEnum(Enum):
            one = "one"
            two = "two"

        class MyEnumListEnvvar(QAIHMStrSetWithEnumEnvvar[MyEnum]):
            SPECIAL_SETTING_ENUM = MyEnum
            ...

        This envvar would parse:
            "one, two, three,four ,four" -> {MyEnum.one, MyEnum.two, 'three', 'four'}
    """

    SPECIAL_SETTING_ENUM: type[EnumT]

    @classmethod
    def parse(cls, value: str) -> set[str | EnumT]:
        values = [x.strip() for x in value.lower().split(",")]
        return {
            (
                cls.SPECIAL_SETTING_ENUM(x)
                if x in cls.SPECIAL_SETTING_ENUM._value2member_map_
                else x
            )
            for x in values
        }

    @classmethod
    def serialize(cls, value: set[str | EnumT]) -> str:
        return ",".join(
            str(x.value) if isinstance(x, cls.SPECIAL_SETTING_ENUM) else str(x)
            for x in value
        )


class QAIHMPathEnvvar(QAIHMEnvvar[Path]):
    """
    Envvar that represents a Path.

    Parses to a Path object.
    """

    @classmethod
    def parse(cls, value: str) -> Path:
        return Path(value)

    @classmethod
    def serialize(cls, value: Path) -> str:
        return str(value)


class QAIHMDateFormatEnvvar:
    """
    2 envvars (date and format) that, together,
    can parse a string Date to a datetime object.
    """

    class DateEnvvar(QAIHMStringEnvvar):
        CLI_ARGNAMES = ["--date"]
        CLI_HELP_MESSAGE = "Date string."

    class FormatEnvvar(QAIHMStringEnvvar):
        CLI_ARGNAMES = ["--date-format"]
        CLI_HELP_MESSAGE = "Date parse string."

    DATE_ENVVAR: type[QAIHMStringEnvvar] = DateEnvvar
    DATE_FORMAT_ENVVAR: type[QAIHMStringEnvvar] = FormatEnvvar
    CLI_DATE_GROUP_NAME: str = "Date"

    @classmethod
    def get(cls, default: datetime | None = None) -> datetime:
        if default is not None:
            date = cls.DATE_ENVVAR.get("")
            if date == "":
                return default
        else:
            date = cls.DATE_ENVVAR.get()
        dformat = cls.DATE_FORMAT_ENVVAR.get()
        return datetime.strptime(date, dformat)

    @classmethod
    def set(cls, date: datetime | str | None, dformat: str | None):
        if isinstance(date, datetime):
            date = cls.serialize(date, dformat or cls.DATE_FORMAT_ENVVAR.get())
        cls.DATE_ENVVAR.set(date)
        cls.DATE_FORMAT_ENVVAR.set(dformat)

    @classmethod
    def patchenv(cls, monkeypatch, date: datetime | str | None, dformat: str | None):
        if isinstance(date, datetime):
            date = cls.serialize(date, dformat or cls.DATE_FORMAT_ENVVAR.get())
        cls.DATE_ENVVAR.patchenv(monkeypatch, date)
        cls.DATE_FORMAT_ENVVAR.patchenv(monkeypatch, dformat)

    @classmethod
    def parse(cls, date: str, dformat: str) -> datetime:
        return datetime.strptime(date, dformat)

    @classmethod
    def serialize(cls, date: datetime, dformat: str) -> str:
        return date.strftime(dformat)

    @classmethod
    def add_arg_group(
        cls,
        parser: argparse.ArgumentParser,
        default_date: datetime | None = None,
        default_format: str | None = None,
        setenv: bool = False,
    ):
        """
        Adds an argument group with 2 args for parsing dates.
        Note that, unlike other envvars, date and format are both returned in un-parsed (string) format.
        Users must use QAIHMDateFormatEnvvar.parse(args.date, args.date_format) to get a datetime object.
        """
        group = parser.add_argument_group(cls.CLI_DATE_GROUP_NAME)
        cls.DATE_ENVVAR.add_arg(
            group,
            (
                cls.serialize(
                    default_date, default_format or cls.DATE_FORMAT_ENVVAR.default()
                )
                if default_date is not None
                else None
            ),
            setenv,
        )
        cls.DATE_FORMAT_ENVVAR.add_arg(group, default_format, setenv)
