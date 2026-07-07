from opentrons import protocol_api

metadata = {"protocolName": "Flex core liquid handling and waste probe"}
requirements = {"robotType": "Flex", "apiLevel": "2.29"}


def run(protocol: protocol_api.ProtocolContext) -> None:
    trash = protocol.load_trash_bin("A3")
    waste_chute = protocol.load_waste_chute()
    tiprack = protocol.load_labware("opentrons_flex_96_tiprack_1000ul", "B3")
    reservoir = protocol.load_labware("nest_12_reservoir_15ml", "C2")
    plate = protocol.load_labware("nest_96_wellplate_200ul_flat", "D2")
    pipette = protocol.load_instrument(
        "flex_1channel_1000", "left", tip_racks=[tiprack]
    )

    protocol.comment("core liquid handling")
    pipette.pick_up_tip()
    pipette.aspirate(100, reservoir["A1"])
    pipette.dispense(80, plate["A1"])
    pipette.blow_out(waste_chute)
    protocol.delay(seconds=1, msg="settle liquid")
    pipette.drop_tip(trash)
