import yaml
import ifcopenshell
import re

from find_adjacent_rooms import adjacent_rooms
from find_adjacent_walls import adjacent_walls
from ifc_data_to_csv import (
    doorinfo_to_csv,
    windowinfo_to_csv,
    room_bounding_walls_to_csv,
    hosts_of_windows_and_doors,
    wall_to_wall_connectivity
)

def find_ifc_storey(ifc_file, storey_name):
    target_storey = None
    for storey in ifc_file.by_type("IfcBuildingStorey"):
        if storey.Name == storey_name:
            target_storey = storey
            break

    if not target_storey:
        print(f"Storey with name '{storey_name}' was not found.")
    else:
        print(f"Storey '{storey_name}' found. OID: {target_storey.id()}")
        return target_storey

def main():

    # Load config.yaml
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)

        ifc_file_path = config["ifc_file"]
        storey_name = config["storey_name"]

    # Open IFC-File
    ifc_file = ifcopenshell.open(ifc_file_path)
    print("IFC file opened successfully.")


    # Find corresponding IfcBuildingStorey
    ifc_storey = find_ifc_storey(ifc_file, storey_name)


    ### Determine adjacent rooms using the room separation line
    spaces_in_storey = adjacent_rooms()

    ### Determine adjacent rooms using door information
    all_doors = ifc_file.by_type("IfcDoor")
    # Filter Doors by storey, extract RoomInfos and Write to .csv
    doorinfo_to_csv(ifc_file, all_doors, ifc_storey)


    ### Determine adjacent rooms using window information
    all_windows = ifc_file.by_type("IfcWindow")
    # Filter Windows by storey, extract RoomInfos and Write to .csv
    windowinfo_to_csv(ifc_file, all_windows, ifc_storey)


    ### Connectivity between Spaces and Walls
    # Extract adjacent Walls to Rooms from IfcRelation
    room_bounding_walls_to_csv(ifc_file, spaces_in_storey)


    ### Host element of Windows and Doors
    hosts_of_windows_and_doors(ifc_file, ifc_storey)


    ### Adjacency of Walls
    #wall_to_wall_connectivity(ifc_file, storey_name)
    adjacent_walls(ifc_file,ifc_storey)


    print("Data created! Done!")

if __name__ == "__main__":
    main()
