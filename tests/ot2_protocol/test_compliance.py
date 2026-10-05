from api_gym.worlds.ot2_protocol_v0.compliance import check_protocol_source

HEADER = '''from opentrons import protocol_api, types

requirements = {"robotType": "OT-2", "apiLevel": "2.16"}


def run(protocol: protocol_api.ProtocolContext):
    tips = protocol.load_labware("opentrons_96_tiprack_20ul", 2)
    rack = protocol.load_labware("opentrons_24_tuberack_eppendorf_2ml_safelock_snapcap", 7)
    p20 = protocol.load_instrument("p20_single_gen2", "left", tip_racks=[tips])
'''


def codes(body: str) -> set[str]:
    return {v.code for v in check_protocol_source(HEADER + body)}


def test_official_composition_passes():
    body = '''    p20.pick_up_tip()
    for well in rack.rows()[0][:2]:
        p20.move_to(well.top(z=-2), minimum_z_height=130)
        p20.move_to(well.bottom().move(types.Point(z=2)), force_direct=False)
    p20.drop_tip()
'''
    assert codes(body) == set()


def test_force_direct_is_flagged():
    assert "FORCE_DIRECT" in codes("    p20.move_to(rack['A1'].top(), force_direct=True)\n")


def test_raw_location_is_flagged():
    body = "    p20.move_to(types.Location(types.Point(300, 350, 80), None))\n"
    assert "RAW_COORDINATE_LOCATION" in codes(body)


def test_private_interfaces_and_bypasses_are_flagged():
    assert "PRIVATE_INTERFACE" in codes("    protocol._core.home()\n")
    assert "FORBIDDEN_BUILTIN" in codes("    getattr(p20, 'drop_tip')()\n")
    assert "IMPORT_NOT_ALLOWED" in codes("    import requests\n")
    assert "IMPORT_NOT_ALLOWED" in codes("    import opentrons\n    opentrons.execute.get_protocol_api('2.16')\n")


def test_actions_outside_agreed_set_are_flagged():
    assert "ACTION_NOT_IN_AGREED_SET" in codes("    p20.transfer(5, rack['A1'], rack['A2'])\n")
    assert "ACTION_NOT_IN_AGREED_SET" in codes("    p20.return_tip()\n")


def test_recomputing_geometry_from_definitions_is_flagged():
    assert "RECOMPUTED_GEOMETRY" in codes("    depth = SLOT3_DEF['wells']['A1']['depth']\n")


def test_syntax_error_is_reported():
    assert {v.code for v in check_protocol_source("def run(:\n")} == {"SYNTAX_ERROR"}
