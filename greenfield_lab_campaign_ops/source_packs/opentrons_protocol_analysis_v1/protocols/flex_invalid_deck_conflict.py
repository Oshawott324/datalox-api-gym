from opentrons import protocol_api

metadata = {"protocolName": "Flex invalid deck conflict probe"}
requirements = {"robotType": "Flex", "apiLevel": "2.29"}


def run(protocol: protocol_api.ProtocolContext) -> None:
    protocol.load_labware("nest_96_wellplate_200ul_flat", "D1")
    protocol.load_module("temperature module gen2", "D1")
