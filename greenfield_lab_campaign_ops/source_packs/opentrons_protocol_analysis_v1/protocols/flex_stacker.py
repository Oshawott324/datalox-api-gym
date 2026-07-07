from opentrons import protocol_api

requirements = {"robotType": "Flex", "apiLevel": "2.25"}

def run(protocol: protocol_api.ProtocolContext):
    stacker = protocol.load_module("flexStackerModuleV1", "D3")
    stacker.set_stored_labware("corning_96_wellplate_360ul_flat", count=2)
    plate = stacker.retrieve()
    stacker.store()
