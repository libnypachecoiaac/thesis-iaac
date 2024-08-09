import yaml
import ifcopenshell
import re

from topologicpy.Topology import Topology

from ifcspaces_to_topology import main as ifcspaces_to_topology
from topology_spaces_to_csv import main as topology_spaces_to_csv
from doorinfo_to_csv import main as doorinfo_to_csv
from windowinfo_to_csv import main as windowinfo_to_csv
from room_bounding_walls_to_csv import main as room_bounding_walls_to_csv

def filter_ifcspaces_by_storey(spaces, storey_name):
    """Filter IfcSpaces by the given storey name."""
    filtered_spaces = []
    for space in spaces:
        for rel in space.Decomposes:
            if rel.is_a("IfcRelAggregates") and rel.RelatingObject.is_a("IfcBuildingStorey"):
                if rel.RelatingObject.Name == storey_name:
                    filtered_spaces.append(space)
                    break
    return filtered_spaces

def filter_spaces_by_name(spaces):
    """Filter IfcSpaces by name containing only digits (1-5 digits)."""
    digit_pattern = re.compile(r'^\d{1,5}$')
    filtered_spaces = []
    for space in spaces:
        if digit_pattern.match(space.Name):
            filtered_spaces.append(space)
    return filtered_spaces

def find_ifc_storey(ifc_file, storey_name):
    """Finding the corresponding IfcBuildingStorey for a given string"""
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

    # Find corresponding IfcBuidlingStorey
    ifc_storey = find_ifc_storey(ifc_file, storey_name)



    ### Determine adjacent rooms using the room separation line

    # Find all IfcSpaces
    all_spaces = ifc_file.by_type("IfcSpace")
    print(f"Number of IfcSpaces found in File: {len(all_spaces)}")

    # Filter spaces by the specified storey name
    spaces_in_storey = filter_ifcspaces_by_storey(all_spaces, storey_name)
    print(f"Number of IfcSpaces matching storey '{storey_name}': {len(spaces_in_storey)}")

    # Further filter spaces by names containing only digits (1-5 digits)
    spaces_in_storey = filter_spaces_by_name(spaces_in_storey)
    print(f"Number of IfcSpaces with valid names: {len(spaces_in_storey)}")

    # Generate a topology from IfcSpaces
    topology_ifcspaces = ifcspaces_to_topology(ifc_file, spaces_in_storey)
    print("Topology of IfcSpaces generated successfully.")

    # Test for shared faces and write to .csv
    topology_spaces_to_csv(topology_ifcspaces)



    ### Determine adjacent rooms using door informations

    # Find all IfcDoors
    all_doors = ifc_file.by_type("IfcDoor")
    # Filter Doors by storey, extract RoomInfos and Write to .csv
    doorinfo_to_csv(ifc_file, all_doors, ifc_storey)



    ### Determine adjacent rooms using window informations

    # Find all IfcWindows
    all_windows = ifc_file.by_type("IfcWindow")
    # Filter Windows by storey, extract RoomInfos and Write to .csv
    windowinfo_to_csv(ifc_file,all_windows,ifc_storey)
    


    ### Connectivity between Spaces and Walls

    # Extract adjacent Walls to Rooms from IfcRelation
    room_bounding_walls_to_csv(ifc_file,ifc_storey, spaces_in_storey)



    ### Hostelement of Windows and Doors



    ### Adjacancy of Walls



if __name__ == "__main__":
    main()