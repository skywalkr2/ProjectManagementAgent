"""Fictional sign-in refusals, classified by response code and the shipped phrases."""

import imaplib
from dataclasses import FrozenInstanceError

import pytest

from engine.connectors.imap_refusal import imap_problem


@pytest.mark.parametrize(
    "message,kind",
    [
        (b"NO [UNAVAILABLE] Rowan's mailbox is under maintenance", "server_busy"),
        ("NO [PRIVACYREQUIRED] Encryption required", "secure_connection_failed"),
        ("NO [AUTHENTICATIONFAILED] Sign-in failed", "credentials_refused"),
        ("NO [AUTHORIZATIONFAILED] Not authorized", "unknown"),
        ("NO [EXPIRED] Credentials expired", "unknown"),
        ("NO [CONTACTADMIN] Contact your administrator", "unknown"),
        ("NO [ALERT] application-specific password required", "app_password_needed"),
        ("NO [AUTHENTICATIONFAILED] incorrect password", "wrong_password"),
        ("NO [ALERT] account is locked", "account_locked"),
        ("NO app password required", "app_password_needed"),
        ("NO account temporarily locked", "account_locked"),
        ("NO imap access is disabled", "sign_in_method_off"),
        ("NO basic authentication is disabled", "sign_in_method_off"),
        ("NO server is busy", "server_busy"),
        ("NO tls negotiation failed", "secure_connection_failed"),
        ("NO mot de passe incorrect pour Rowan", "wrong_password"),
        ("NO contraseña incorrecta para Rowan", "wrong_password"),
        ("NO Konto ist gesperrt", "account_locked"),
        ("NO アプリパスワードが必要", "app_password_needed"),
        ("NO 原因は不明です", "unknown"),
        (b"NO invalid byte \xff", "unknown"),
        ("", "unknown"),
        ("NO [ALERT] Please read this notice", "unknown"),
        ("NO [NOPERM] Access refused", "unknown"),
        ("NO [NEWCODE] Refused", "unknown"),
        ("NO [unavailable] incorrect password", "server_busy"),
        ("NO [PRIVACYREQUIRED] server is busy", "secure_connection_failed"),
        ("NO [AUTHENTICATIONFAILED] application-specific password required", "app_password_needed"),
        ("NO account is locked; incorrect password", "unknown"),
        ("NO Rowan at rowan@example.com cannot sign in", "unknown"),
    ],
)
def test_fictional_refusals(message, kind):
    problem = imap_problem(message, "mail.example.com")
    assert problem.kind == kind
    assert problem.reason
    assert problem.advice_key
    assert isinstance(problem.text, str)


def test_long_address():
    address = "https" + "://help.example.com/" + "private/" * 2000 + "?token=secret#section"
    problem = imap_problem("NO [ALERT] app password required: " + address, "mail.example.com")
    assert problem.text == "NO [ALERT] app password required: help.example.com"
    assert problem.kind == "app_password_needed"


@pytest.mark.parametrize("prefix", ["https" + "://", "http" + "://", "www."])
def test_address_credentials_ports_and_punctuation(prefix):
    address = prefix + (
        "help.example.com/path?q=secret" if prefix == "www." else "rowan:secret@help.example.com:8443/path?q=secret"
    )
    expected = "www.help.example.com" if prefix == "www." else "help.example.com"
    assert imap_problem("See (" + address + ").", "mail.example.com").text == "See (" + expected + ")."


def test_bare_address_and_email():
    address = "help.example.com" + "/account?token=secret"
    result = imap_problem(address + " rowan@example.com", "mail.example.com")
    assert result.text == "help.example.com rowan@example.com"


def test_code_conflict():
    assert imap_problem("[UNAVAILABLE] [PRIVACYREQUIRED]", "mail.example.com").kind == "unknown"


def test_scoped_rules():
    rules = [{"phrase": "special refusal", "kind": "account_locked", "hosts": ["mail.example.com"]}]
    assert imap_problem("special refusal", "MAIL.EXAMPLE.COM.", rules=rules).kind == "account_locked"
    assert imap_problem("special refusal", "other.example.com", rules=rules).kind == "unknown"


def test_no_phrase_data_does_not_guess():
    assert imap_problem("app password required", "mail.example.com", rules=[]).kind == "unknown"


def test_decoding():
    assert imap_problem(b"Refused \xff", "mail.example.com").text == "Refused \ufffd"


@pytest.mark.parametrize(
    "rules", [{}, [{}], [{"phrase": "", "kind": "wrong_password"}], [{"phrase": "x", "kind": "invented"}]]
)
def test_bad_rules(rules):
    with pytest.raises(ValueError):
        imap_problem("Refused", "mail.example.com", rules=rules)


def test_immutable_result():
    result = imap_problem("Refused", "mail.example.com")
    with pytest.raises(FrozenInstanceError):
        result.kind = "wrong_password"


def test_the_refusal_as_imaplib_turns_it_into_text():
    error = imaplib.IMAP4.error(b"[AUTHENTICATIONFAILED] Invalid credentials (Failure)")
    for given in (str(error), error.args[0]):
        problem = imap_problem(given, "mail.example.com")
        assert problem.kind == "credentials_refused"
        assert problem.advice_key == "check_credentials"
        assert problem.text == "[AUTHENTICATIONFAILED] Invalid credentials (Failure)"


def test_a_specific_phrase_outranks_credentials_refused():
    refusal = "[AUTHENTICATIONFAILED] Invalid credentials; application-specific password required"
    assert imap_problem(refusal, "mail.example.com").kind == "app_password_needed"


def test_text_that_only_looks_like_bytes_stays_as_is():
    assert imap_problem("b'unterminated", "mail.example.com").text == "b'unterminated"
