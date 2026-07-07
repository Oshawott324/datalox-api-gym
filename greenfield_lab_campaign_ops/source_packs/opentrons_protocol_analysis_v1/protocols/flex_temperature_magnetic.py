from opentrons import protocol_api

metadata = {"protocolName": "Flex temperature and magnetic module probe"}
requirements = {"robotType": "Flex", "apiLevel": "2.29"}


def run(protocol: protocol_api.ProtocolContext) -> None:
    temp = protocol.load_module("temperature module gen2", "D1")
    temp.load_labware("opentrons_24_aluminumblock_nest_1.5ml_snapcap")
    temp.set_temperature(10)
    temp.deactivate()

    mag = protocol.load_module("magneticBlockV1", "C1")
    mag.load_labware("nest_96_wellplate_200ul_flat")
