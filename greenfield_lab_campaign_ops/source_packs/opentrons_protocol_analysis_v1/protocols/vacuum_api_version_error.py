from opentrons import protocol_api

requirements = {"robotType": "Flex", "apiLevel": "2.29"}

def run(protocol: protocol_api.ProtocolContext):
    vac = protocol.load_module("vacuumModuleV1", "A3")
    vac.load_labware("nest_96_wellplate_100ul_pcr_full_skirt")
    vac.start_set_vacuum_power(40, duration_s=5, vent_after=True)
