import ifcopenshell
import re
import networkx as nx
import csv
import os
import yaml
import pickle


# Function to filter IfcSpaces by storey name
def filter_ifcspaces_by_storey(spaces, storey_name):
    filtered_spaces = []
    for space in spaces:
        for rel in space.Decomposes:
            if rel.is_a("IfcRelAggregates") and rel.RelatingObject.is_a("IfcBuildingStorey"):
                if rel.RelatingObject.Name == storey_name:
                    filtered_spaces.append(space)
                    break
    return filtered_spaces

# Function to filter IfcSpaces by name with digits (1-5 digits)
def filter_spaces_by_name(spaces):
    digit_pattern = re.compile(r'^\d{1,5}$')
    filtered_spaces = []
    for space in spaces:
        if digit_pattern.match(space.Name):
            filtered_spaces.append(space)
    return filtered_spaces

# Function to process "Direct" connections from Output01_RoomToRoom_BySeparationLine.csv
def process_direct_connections(G, csv_file):
    edges = []
    with open(csv_file, 'r') as file:
        for line in file:
            parts = line.strip().split(';')
            main_room_global_id = parts[0]
            if len(parts) > 1:
                connected_rooms_global_ids = parts[1].split(',')
                for neighbor_global_id in connected_rooms_global_ids:
                    # Filter self-references
                    if main_room_global_id != neighbor_global_id:
                        edges.append((main_room_global_id, neighbor_global_id))
    
    for edge in edges:
        room1 = None
        room2 = None
        for node in G.nodes:
            if G.nodes[node]["GlobalId"] == edge[0]:
                room1 = node
            if G.nodes[node]["GlobalId"] == edge[1]:
                room2 = node
        if room1 and room2:
            G.add_edge(room1, room2, Access="Direct")

# Function to process "Door" and "Window" connections from respective CSVs
def process_element_connections(G, csv_file, access_type):
    element_edges = []
    with open(csv_file, 'r') as file:
        for line in file:
            parts = line.strip().split(';')
            element_global_id = parts[0]
            if len(parts) > 1:
                connected_rooms_global_ids = parts[1].split(',')
                for i in range(len(connected_rooms_global_ids) - 1):
                    for j in range(i + 1, len(connected_rooms_global_ids)):
                        # Filter self-references
                        if connected_rooms_global_ids[i] != connected_rooms_global_ids[j]:
                            element_edges.append((connected_rooms_global_ids[i], connected_rooms_global_ids[j]))

    for edge in element_edges:
        room1 = None
        room2 = None
        for node in G.nodes:
            if G.nodes[node]["GlobalId"] == edge[0]:
                room1 = node
            if G.nodes[node]["GlobalId"] == edge[1]:
                room2 = node
        if room1 and room2:
            G.add_edge(room1, room2, Access=access_type)

# Function to add doors and windows as nodes and edges
def process_doors_and_windows(G, ifc_file, csv_file, element_type, color, category):
    edges = []
    elements = set()
    with open(csv_file, 'r') as file:
        for line in file:
            parts = line.strip().split(';')
            element_global_id = parts[0]
            connected_rooms_global_ids = parts[1].split(',') if len(parts) > 1 else []
            
            element = next((e for e in ifc_file.by_type(element_type) if e.GlobalId == element_global_id), None)
            
            if element:
                element_oid = element.id()
                elements.add((f"{element_type.split('Ifc')[-1]}_{element_oid}", element_global_id, element_oid))
            
                for room_global_id in connected_rooms_global_ids:
                    edges.append((element_oid, room_global_id))
    
    for element_name, element_global_id, element_oid in elements:
        G.add_node(element_name, color=color, GlobalId=element_global_id, OID=element_oid)
    
    for edge in edges:
        element = f"{element_type.split('Ifc')[-1]}_{edge[0]}"
        room = None
        for node in G.nodes:
            if G.nodes[node]["GlobalId"] == edge[1]:
                room = node
                break
        if room:
            G.add_edge(element, room, Category=category)

# Function to process the CSV file for Hosts (Windows/Doors) and Walls
def process_element_hosts(G, ifc_file, csv_file, all_walls):
    def get_element_oid_by_guid(elements, guid):
        for element in elements:
            if element.GlobalId == guid:
                return element.id()
        return None
    
    with open(csv_file, 'r') as file:
        reader = csv.reader(file, delimiter=';')
        for row in reader:
            element_type = row[0]  # e.g., "IfcDoor" or "IfcWindow"
            element_guid = row[1]  # GlobalId of the window or door
            wall_guid = row[2]     # GlobalId of the wall in which the element is hosted

            # Get the OID of the element
            element_oid = get_element_oid_by_guid(ifc_file.by_type(element_type), element_guid)
            if element_oid is not None:
                element_node = f"{element_type.split('Ifc')[-1]}_{element_oid}"
                
                # Get the OID of the wall
                wall_oid = get_element_oid_by_guid(all_walls, wall_guid)
                if wall_oid is not None:
                    wall_node = f"Wall_{wall_oid}"
                    
                    if element_node in G and wall_node in G:
                        G.add_edge(element_node, wall_node, Category="HostedBy")

# Function to filter IfcWalls by storey name and add them as nodes
def process_walls(G, ifc_file, storey_name):
    def get_storey(element):
        for rel in element.ContainedInStructure:
            if rel.is_a("IfcRelContainedInSpatialStructure") and rel.RelatingStructure.is_a("IfcBuildingStorey"):
                return rel.RelatingStructure
        return None

    all_walls = ifc_file.by_type("IfcWall")
    walls_in_storey = []
    for wall in all_walls:
        storey = get_storey(wall)
        if storey and storey.Name == storey_name:
            walls_in_storey.append((wall.id(), wall.GlobalId))
    
    for wall_oid, wall_global_id in walls_in_storey:
        node_label = f"Wall_{wall_oid}"
        G.add_node(node_label, color='grey', GlobalId=wall_global_id, OID=wall_oid)

# Function to process the CSV files for walls and rooms
def process_walls_and_rooms(G, csv_file, all_walls, relation):
    def get_wall_oid_by_guid(walls, guid):
        for wall in walls:
            if wall.GlobalId == guid:
                return wall.id()
        return None
    
    with open(csv_file, 'r') as file:
        reader = csv.reader(file, delimiter=';')
        for row in reader:
            space_global_id = row[0]
            wall_guids = row[1].split(',')
            space_node = None
            for node in G.nodes:
                if G.nodes[node].get("GlobalId") == space_global_id:
                    space_node = node
                    break
            if space_node:
                for wall_guid in wall_guids:
                    wall_oid = get_wall_oid_by_guid(all_walls, wall_guid)
                    if wall_oid is not None:
                        wall_node = f"Wall_{wall_oid}"
                        if wall_node in G:
                            G.add_edge(space_node, wall_node, Category=relation)

# Function to process the CSV file for adjacent walls
def process_wall_adjacency(G, csv_file, all_walls):
    def get_wall_oid_by_guid(walls, guid):
        for wall in walls:
            if wall.GlobalId == guid:
                return wall.id()
        return None
    
    with open(csv_file, 'r') as file:
        reader = csv.reader(file, delimiter=';')
        for row in reader:
            primary_wall_guid = row[0]
            connected_wall_guids = row[1].split(',')
            primary_wall_oid = get_wall_oid_by_guid(all_walls, primary_wall_guid)
            if primary_wall_oid is not None:
                primary_wall_node = f"Wall_{primary_wall_oid}"
                for connected_wall_guid in connected_wall_guids:
                    connected_wall_oid = get_wall_oid_by_guid(all_walls, connected_wall_guid)
                    if connected_wall_oid is not None:
                        connected_wall_node = f"Wall_{connected_wall_oid}"
                        if primary_wall_node in G and connected_wall_node in G:
                            G.add_edge(primary_wall_node, connected_wall_node, Category="IsConnected")

# MAIN
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

    # Open IFC file
    ifc_file = ifcopenshell.open(ifc_file_path)
    print("IFC file opened successfully.")

    # Create Graph
    G = nx.Graph()

    # Load and filter Rooms
    all_spaces = ifc_file.by_type("IfcSpace")
    spaces = filter_ifcspaces_by_storey(all_spaces, storey_name)
    spaces = filter_spaces_by_name(spaces)

    # Add Spaces as Nodes
    for space in spaces:
        node_label = f"Room_{space.Name}"
        global_id = space.GlobalId
        G.add_node(node_label, color='yellow', GlobalId=global_id)

    # Room-Room Connection "Direct"
    process_direct_connections(G, csv_room_to_room)

    # Room-Room Connection "Door"
    process_element_connections(G, csv_doors, "Door")

    # Room-Room Connection "Window"
    process_element_connections(G, csv_windows, "Window")

    # Add Doors as Nodes
    process_doors_and_windows(G, ifc_file, csv_doors, "IfcDoor", 'blue', "ContainedIn")

    # Add Windows as Nodes
    process_doors_and_windows(G, ifc_file, csv_windows, "IfcWindow", 'purple', "ContainedIn")

    # Add Walls as Nodes
    process_walls(G, ifc_file, storey_name)

    # Connect Rooms and Walls
    process_walls_and_rooms(G, csv_walls, ifc_file.by_type("IfcWall"), "ContainedIn")

    # Connect Walls to Walls
    process_wall_adjacency(G, csv_wall_adjacency, ifc_file.by_type("IfcWall"))

    # Connect Windows and Doors with Host
    process_element_hosts(G, ifc_file, csv_host_elements, ifc_file.by_type("IfcWall"))

    # Save the graph using pickle
    with open("network_graph.pkl", "wb") as f:
        pickle.dump(G, f)

    print("Graph saved successfully.")

if __name__ == "__main__":
    main()
