import yaml
import ifcopenshell
import logging
import re
from ifc_data_to_csv import (
    doorinfo_to_csv,
    windowinfo_to_csv,
    room_bounding_walls_to_csv,
    hosts_of_windows_and_doors,
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


def filter_ifcspaces_by_storey(spaces, storey_name):
    filtered_spaces = []
    for space in spaces:
        for rel in space.Decomposes:
            if rel.is_a("IfcRelAggregates") and rel.RelatingObject.is_a("IfcBuildingStorey"):
                if rel.RelatingObject.Name == storey_name:
                    filtered_spaces.append(space)
                    break
    return filtered_spaces

def filter_spaces_by_name(spaces):
    # For 0301
    # if True:
    #     exclude_pattern = re.compile(r'(-10$|^Area:)')
    #     filtered_spaces = []
        
    #     for space in spaces:
    #         if not exclude_pattern.search(space.Name):
    #             filtered_spaces.append(space)
    #     return filtered_spaces

    # For HUS28
    # digit_pattern = re.compile(r'^\d{1,5}$')
    # filtered_spaces = []
    # for space in spaces:
    #     if digit_pattern.match(space.Name):
    #         filtered_spaces.append(space)
    # return filtered_spaces

    # For 3501
    exclude_pattern = re.compile(r'^Area:|[-]')
    filtered_spaces = []
    for space in spaces:
        if not exclude_pattern.search(space.Name):
            filtered_spaces.append(space)
    return filtered_spaces



# Setup logging
logging.basicConfig(filename='debug.log', level=logging.DEBUG, format='%(asctime)s %(levelname)s: %(message)s')

# Load config.yaml
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

ifc_file_path = config["ifc_file"]
storey_name = config["storey_name"]

# Load IFC
ifc_file = ifcopenshell.open(ifc_file_path)

# Find all IfcSpaces
ifc_spaces = ifc_file.by_type("IfcSpace")
print(f"Number of IfcSpaces found in File: {len(ifc_spaces)}")

# Find corresponding IfcBuildingStorey
ifc_storey = find_ifc_storey(ifc_file, storey_name)

# Filter Spaces by storey
ifc_spaces = filter_ifcspaces_by_storey(ifc_spaces, storey_name)
print(f"Amount of IfcSpaces in specified storey'{storey_name}': {len(ifc_spaces)}")

# Further filter spaces by names containing only digits (1-5 digits)
ifc_spaces = filter_spaces_by_name(ifc_spaces)
print(f"Number of IfcSpaces with valid names: {len(ifc_spaces)}")

# Filter spaces by the specified storey name
spaces_in_storey = filter_ifcspaces_by_storey(ifc_spaces, storey_name)
print(f"Number of IfcSpaces matching storey '{storey_name}': {len(spaces_in_storey)}")

# Find all IfcDoors
all_doors = ifc_file.by_type("IfcDoor")
# Filter Doors by storey, extract RoomInfos and Write to .csv
doorinfo_to_csv(ifc_file, all_doors, ifc_storey)

### Determine adjacent rooms using window information

# Find all IfcWindows
all_windows = ifc_file.by_type("IfcWindow")
# Filter Windows by storey, extract RoomInfos and Write to .csv
windowinfo_to_csv(ifc_file, all_windows, ifc_storey)

### Connectivity between Spaces and Walls

# Extract adjacent Walls to Rooms from IfcRelation
room_bounding_walls_to_csv(ifc_file, spaces_in_storey)

### Host element of Windows and Doors
hosts_of_windows_and_doors(ifc_file, ifc_storey)