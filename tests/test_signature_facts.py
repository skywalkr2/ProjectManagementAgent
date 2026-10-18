from dataclasses import FrozenInstanceError

import pytest

from engine.signature_facts import signature_facts


@pytest.mark.parametrize(
    "signature,phones,titles,organizations,websites",
    [
        ("Rowan Vale\nTitle: Consultant\nCompany: Alder Circle\nPhone: +1 202 555 0101\nWeb: example.com", 1, 1, 1, 1),
        ("Mira Fen\nEditor\nOrganization: Fern Press\nTel: (202) 555-0102", 1, 1, 1, 0),
        ("Oren Reed\nDesigner\nMobile: +44 7700 900123", 1, 1, 0, 0),
        ("Tess Alder\nRole: Project Manager\nCompany: Willow Studio", 0, 1, 1, 0),
        ("Lena Marsh\nIndependent Consultant\nexample.com/contact", 0, 1, 0, 1),
        ("Dev Moss\nPhone: +1 202 555 0103 | Mobile: +1 202 555 0104", 2, 0, 0, 0),
        ("Nia Fern\nTel: +1 202 555 0105\nFax: +1 202 555 0106\nCell: +1 202 555 0107", 3, 0, 0, 0),
        ("Ravi Linden\nTitle: Architect\nTel: 202-555-0108 ext. 42", 1, 1, 0, 0),
        ("Esme Vale\nSenior Editor\nEmployer: Birch Letter", 0, 1, 1, 0),
        ("Kian Grove\nManaging Director\nCompany: Moss Circle", 0, 1, 1, 0),
        ("Alia Brook\nFounder & Designer\nOrganisation: Reed Workshop", 0, 1, 1, 0),
        ("Ivo Reed\nWe promise results beyond expectations.", 0, 0, 0, 0),
        ("Mira Designer\nDelivering tomorrow, today.", 0, 0, 0, 0),
        ("Rowan Vale\nYour success is our job title.", 0, 0, 0, 0),
        (
            "Oren Reed\nTitle: Translator\nConfidential: This message is for its recipient.\nPhone: +1 202 555 0109",
            0,
            1,
            0,
            0,
        ),
        ("Tess Alder\nPhone: +1 202 555 0110\nLegal notice\nCompany: Fictional Notice Office", 1, 0, 0, 0),
        ("Lena Marsh\nThis email may contain confidential material.\nexample.com/legal", 0, 0, 0, 0),
        ("Dev Moss\nSent from my pocket device", 0, 0, 0, 0),
        ("Nia Fern\nCompany: Clover Desk\nWeb: studio.example.com/about?ref=fictional", 0, 0, 1, 1),
        ("Ravi Linden\nWeb: WWW.EXAMPLE.COM/contact", 0, 0, 0, 1),
        ("Esme Vale\nexample.com/work\nnotes.example.com", 0, 0, 0, 2),
        ("Kian Grove\nkian@example.com", 0, 0, 0, 0),
        ("Alia Brook\nOrganisation: Juniper Circle\nOffice: 202 555 0111", 1, 0, 1, 0),
        ("Ivo Reed\nDirect: +1 (202) 555-0112 x9", 1, 0, 0, 0),
        ("Mira Fen\nCompany: Meadow Letter\nFounded 2020\n48 Alder Lane", 0, 0, 1, 0),
        ("Oren Reed\n2027-01-05\nAppointment reference 123456789", 0, 0, 0, 0),
        ("Tess Alder\nPosition: Researcher\nWe will always go the extra mile.", 0, 1, 0, 0),
        ("Lena Marsh\nTitle: Editor\nRole: Consultant\nCompany: Fern Circle", 0, 2, 1, 0),
        ("Dev Moss\nCompany: Alder Desk\nEmployer: Willow Workshop", 0, 0, 2, 0),
        ("  Rowan Vale  \n  Phone: +1 202 555 0113  \n  Title: Illustrator  \n", 1, 1, 0, 0),
    ],
)
def test_thirty_fictional_signatures(signature, phones, titles, organizations, websites):
    result = signature_facts(signature)
    assert len(result.phones) == phones
    assert len(result.job_titles) == titles
    assert len(result.organizations) == organizations
    assert len(result.websites) == websites
    lines = signature.splitlines()
    for fact in (*result.phones, *result.job_titles, *result.organizations, *result.websites):
        assert fact.evidence in lines
        assert fact.value


def test_exact_line_preserves_spaces():
    line = "  Phone: +1 202 555 0113  "
    result = signature_facts("Rowan Vale\n" + line)
    assert result.phones[0].evidence == line
    assert result.phones[0].value == "+1 202 555 0113"


def test_domain_only_with_credentials_port_and_path():
    address = "https" + "://rowan:fictional@Studio.Example.com:8443/contact?token=fictional#team"
    line = "Web: " + address
    result = signature_facts("Rowan Vale\n" + line)
    assert result.websites[0].value == "studio.example.com"
    assert result.websites[0].evidence == line


def test_email_does_not_become_website():
    assert not signature_facts("Rowan Vale\nrowan@studio.example.com").websites


def test_title_never_inferred_from_name():
    result = signature_facts("Rowan Editor\nAlder Consulting")
    assert not result.job_titles
    assert not result.organizations
    assert any(item.field == "job_title" and "unknown" in item.reason for item in result.unknown)


def test_first_line_role_word_is_not_assumed_title():
    assert not signature_facts("Editor\nrowan@example.com").job_titles


def test_blank_fields_unknown():
    result = signature_facts("Rowan Vale\nTitle:\nCompany:")
    assert not result.job_titles and not result.organizations
    assert any("no value" in item.reason for item in result.unknown)


def test_long_phone_rejected():
    result = signature_facts("Rowan Vale\nPhone: +12345678901234567890")
    assert not result.phones
    assert any("digit count" in item.reason for item in result.unknown)


def test_no_country_code_invented():
    result = signature_facts("Rowan Vale\nPhone: 202 555 0114")
    assert result.phones[0].value == "202 555 0114"


def test_multiple_phone_extensions():
    result = signature_facts("Rowan Vale\nTel: +1 202 555 0115 ext. 2 | Fax: +1 202 555 0116 x3")
    assert [fact.value for fact in result.phones] == ["+1 202 555 0115 ext. 2", "+1 202 555 0116 x3"]


def test_empty():
    result = signature_facts("")
    assert len(result.unknown) == 4


def test_frozen_deterministic():
    text = "Rowan Vale\nTitle: Editor"
    first = signature_facts(text)
    assert signature_facts(text) == first
    with pytest.raises(FrozenInstanceError):
        first.job_titles[0].value = "Other"


def test_credential_is_not_a_website():
    result = signature_facts("Rowan Vale, B.Sc.\nTitle: Editor")
    assert not result.websites


def test_slogan_domain_like_word_not_inferred_website():
    result = signature_facts("Rowan Vale\nYour success.starts.here every day.")
    assert not result.websites


def test_unknown_input():
    result = signature_facts(None)
    assert result.unknown[0].field == "signature"
