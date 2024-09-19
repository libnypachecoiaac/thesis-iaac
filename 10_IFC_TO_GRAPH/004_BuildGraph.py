import ifcopenshell
import yaml
import re
from neo4j import GraphDatabase

from neo4j_functions import (
    create_ifcspace_nodes, 
    process_doors_and_windows, 
    process_walls, 
    process_walls_and_rooms, 
    process_wall_adjacency, 
    process_element_hosts, 
    process_direct_connections, 
    process_element_connections,
    process_furniture,
    cleanup_isolated_nodes
)

def filter_spaces_by_category(spaces, category_value="Rooms"):
    filtered_spaces = []
    
    for space in spaces:
        # Get the property sets of the space
        property_sets = space.IsDefinedBy
        
        # Iterate through the property sets and find the 'Other' set with Category
        for prop_set in property_sets:
            if hasattr(prop_set, "RelatingPropertyDefinition"):
                props = prop_set.RelatingPropertyDefinition
                
                # Check if it's a property set and contains the 'Category' property
                if hasattr(props, "HasProperties"):
                    for prop in props.HasProperties:
                        if prop.Name == "Category" and prop.NominalValue.wrappedValue == category_value:
                            filtered_spaces.append(space)
                            break
                           
    return filtered_spaces

def filter_ifcspaces_by_storey(spaces, storey_name):
    filtered_spaces = []
    for space in spaces:
        for rel in space.Decomposes:
            if rel.is_a("IfcRelAggregates") and rel.RelatingObject.is_a("IfcBuildingStorey"):
                if rel.RelatingObject.Name == storey_name:
                    filtered_spaces.append(space)
                    break
    return filtered_spaces

def main():
    # Paths
    csv_room_to_room = "Output01_RoomToRoom_BySeparationLine.csv"
    csv_doors = "Output02_RoomToRoom_ByDoors.csv"
    csv_windows = "Output03_RoomToRoom_ByWindows.csv"
    csv_walls = "Output04_RoomBoundingWalls.csv"
    csv_wall_adjacency = "Output06_Wall_Adjacancy.csv"
    csv_host_elements = "Output05_Hosts_of_WindowsAndDoors.csv"

    # Load config.yaml
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)

    ifc_file_path = config["ifc_file"]
    storey_name = config["storey_name"]
    username = config["username"]
    password = config["password"]


    # Open IFC file
    ifc_file = ifcopenshell.open(ifc_file_path)
    print("IFC file opened successfully.")

    # Load and filter Rooms
    all_spaces = ifc_file.by_type("IfcSpace")
    spaces = filter_ifcspaces_by_storey(all_spaces, storey_name)
    spaces = filter_spaces_by_category(spaces)

    # Connect to Neo4J
    uri = "bolt://localhost:7687"
    driver = GraphDatabase.driver(uri, auth=(username, password))

    # Create Nodes and write Data
    create_ifcspace_nodes(driver, spaces, storey_name)

    # Add Doors and Window as Nodes and add connections to rooms
    process_doors_and_windows(driver, ifc_file, csv_doors, "IfcDoor", "Door", storey_name)
    process_doors_and_windows(driver, ifc_file, csv_windows, "IfcWindow", "Window", storey_name)

    # Add Walls
    process_walls(driver, ifc_file, storey_name)

    # Connect Walls with rooms
    process_walls_and_rooms(driver, csv_walls, ifc_file.by_type("IfcWall"))

    # Connect Walls to each other
    process_wall_adjacency(driver, csv_wall_adjacency, ifc_file.by_type("IfcWall"))

    # Connect Windows and Doors to their Host
    process_element_hosts(driver, ifc_file, csv_host_elements, ifc_file.by_type("IfcWall"))

    # Create Connections between Rooms
    process_direct_connections(driver, csv_room_to_room)
    process_element_connections(driver, csv_doors, "Door")
    process_element_connections(driver, csv_windows, "Window")

    # Add Furniture
    process_furniture(driver, ifc_file, storey_name)

    # Clean up isolated Nodes
    cleanup_isolated_nodes(driver, storey_name)

    # Close Neo4j
    driver.close()
    print("IfcSpaces, Türen, Fenster, Wände und Verbindungen wurden erfolgreich in Neo4j importiert.")

if __name__ == "__main__":
    main()
