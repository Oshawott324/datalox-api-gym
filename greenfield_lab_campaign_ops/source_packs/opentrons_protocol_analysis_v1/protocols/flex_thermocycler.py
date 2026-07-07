from opentrons import protocol_api

metadata = {"protocolName": "Flex thermocycler probe"}
requirements = {"robotType": "Flex", "apiLevel": "2.29"}


def run(protocol: protocol_api.ProtocolContext) -> None:
    tc = protocol.load_module("thermocycler module gen2")
    tc.open_lid()
    tc.load_labware("nest_96_wellplate_100ul_pcr_full_skirt")
    tc.set_lid_temperature(100)
    tc.close_lid()
    tc.set_block_temperature(95, hold_time_seconds=5, block_max_volume=50)
    tc.execute_profile(
        steps=[
            {"temperature": 60, "hold_time_seconds": 2},
            {"temperature": 72, "hold_time_seconds": 2},
        ],
        repetitions=2,
        block_max_volume=50,
    )
    tc.open_lid()
    tc.deactivate_lid()
    tc.deactivate_block()
