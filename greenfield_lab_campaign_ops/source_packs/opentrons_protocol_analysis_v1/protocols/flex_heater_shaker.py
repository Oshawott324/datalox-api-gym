from opentrons import protocol_api

metadata = {"protocolName": "Flex heater-shaker probe"}
requirements = {"robotType": "Flex", "apiLevel": "2.29"}


def run(protocol: protocol_api.ProtocolContext) -> None:
    hs = protocol.load_module("heaterShakerModuleV1", "D1")
    hs.open_labware_latch()
    hs.load_labware("nest_96_wellplate_200ul_flat")
    hs.close_labware_latch()
    hs.set_and_wait_for_temperature(37)
    hs.set_and_wait_for_shake_speed(500)
    hs.deactivate_shaker()
    hs.deactivate_heater()
    hs.open_labware_latch()
