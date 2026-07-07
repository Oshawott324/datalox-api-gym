from opentrons import protocol_api

metadata = {"protocolName": "Flex absorbance reader and gripper probe"}
requirements = {"robotType": "Flex", "apiLevel": "2.29"}


def run(protocol: protocol_api.ProtocolContext) -> None:
    reader = protocol.load_module("absorbanceReaderV1", "D3")
    reader.open_lid()
    plate = reader.load_labware("nest_96_wellplate_200ul_flat")
    reader.close_lid()
    reader.initialize("single", [450])
    reader.read(export_filename="absorbance_probe.csv")
    reader.open_lid()
    protocol.move_labware(plate, "C2", use_gripper=True)
