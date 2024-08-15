import ifcopenshell
import re
import yaml
from neo4j import GraphDatabase
import csv

# Funktion, um IfcSpaces nach Geschossname zu filtern
def filter_ifcspaces_by_storey(spaces, storey_name):
    filtered_spaces = []
    for space in spaces:
        for rel in space.Decomposes:
            if rel.is_a("IfcRelAggregates") and rel.RelatingObject.is_a("IfcBuildingStorey"):
                if rel.RelatingObject.Name == storey_name:
                    filtered_spaces.append(space)
                    break
    return filtered_spaces

# Funktion, um IfcSpaces nach Namen mit Ziffern (1-5 Ziffern) zu filtern
def filter_spaces_by_name(spaces):
    digit_pattern = re.compile(r'^\d{1,5}$')
    filtered_spaces = []
    for space in spaces:
        if digit_pattern.match(space.Name):
            filtered_spaces.append(space)
    return filtered_spaces

# Funktion, um IfcSpaces als Knoten in Neo4j anzulegen und mit zusätzlichen Daten anzureichern
def create_ifcspace_nodes(driver, spaces):
    with driver.session() as session:
        for space in spaces:
            # Zusätzliche Attribute aus der IFC-Datei extrahieren
            global_id = space.GlobalId
            long_name = decode_ifc_text(space.LongName) if space.LongName else 'N/A'
            area = extract_property_value(space, 'Gross Floor Area', 'area')
            height = extract_property_value(space, 'Height', 'number')
            is_external = extract_property_value(space, 'IsExternal', 'bool')
            comments = extract_property_value(space, 'Comments', 'text')
            
            # Knoten erstellen und mit zusätzlichen Daten anreichern
            session.write_transaction(
                add_space_node, global_id, space.id(), long_name, area, height, is_external, comments
            )

def add_space_node(tx, global_id, oid, long_name, area, height, is_external, comments):
    tx.run(
        """
        MERGE (n:Room {GlobalId: $global_id})
        ON CREATE SET n.Object = 'Room', n.OID = $oid
        SET n.LongName = $long_name,
            n.Area = $area,
            n.Height = $height,
            n.IsExternal = $is_external,
            n.Comments = $comments
        """,
        global_id=global_id,
        oid=oid,
        long_name=long_name,
        area=area,
        height=height,
        is_external=is_external,
        comments=comments
    )

# Funktion, um direkte Verbindungen zwischen Räumen herzustellen
def process_direct_connections(driver, csv_file):
    with driver.session() as session:
        with open(csv_file, 'r') as file:
            for line in file:
                parts = line.strip().split(';')
                main_room_global_id = parts[0]
                if len(parts) > 1:
                    connected_rooms_global_ids = parts[1].split(',')
                    for neighbor_global_id in connected_rooms_global_ids:
                        if main_room_global_id != neighbor_global_id:
                            room_pair = sorted([main_room_global_id, neighbor_global_id])  # Sortieren der IDs
                            session.write_transaction(
                                add_edge, room_pair[0], room_pair[1], "Direct"
                            )

# Funktion, um Türen- und Fensterverbindungen zwischen Räumen herzustellen
def process_element_connections(driver, csv_file, access_type):
    with driver.session() as session:
        with open(csv_file, 'r') as file:
            for line in file:
                parts = line.strip().split(';')
                element_global_id = parts[0]
                if len(parts) > 1:
                    connected_rooms_global_ids = parts[1].split(',')
                    for i in range(len(connected_rooms_global_ids) - 1):
                        for j in range(i + 1, len(connected_rooms_global_ids)):
                            if connected_rooms_global_ids[i] != connected_rooms_global_ids[j]:
                                room_pair = sorted([connected_rooms_global_ids[i], connected_rooms_global_ids[j]])  # Sortieren der IDs
                                session.write_transaction(
                                    add_edge, room_pair[0], room_pair[1], access_type
                                )

# Funktion, um eine Verbindung zwischen zwei Räumen in Neo4j anzulegen
def add_edge(tx, room1_global_id, room2_global_id, access_type):
    tx.run(
        """
        MATCH (a:Room {GlobalId: $room1_global_id}), (b:Room {GlobalId: $room2_global_id})
        MERGE (a)-[r:ACCESS {Access: $access_type}]->(b)
        """,
        room1_global_id=room1_global_id,
        room2_global_id=room2_global_id,
        access_type=access_type
    )

# Funktion zum Dekodieren von Unicode-Sonderzeichen in IFC-TEXT
def decode_ifc_text(text):
    matches = re.findall(r'\\X\\([0-9A-Fa-f]{4})', text)
    for match in matches:
        text = text.replace(r'\X\{}'.format(match), chr(int(match, 16)))
    return text

# Funktion zum Extrahieren von Property-Werten aus IFC-Dateien
def extract_property_value(ifc_element, property_name, value_type):
    for rel in ifc_element.IsDefinedBy:
        if rel.is_a("IfcRelDefinesByProperties"):
            props = rel.RelatingPropertyDefinition
            if props.is_a("IfcPropertySet"):
                for prop in props.HasProperties:
                    if prop.Name == property_name:
                        if value_type == 'text' and hasattr(prop.NominalValue, 'wrappedValue'):
                            return decode_ifc_text(prop.NominalValue.wrappedValue)
                        elif value_type == 'number' and hasattr(prop.NominalValue, 'wrappedValue'):
                            return round(prop.NominalValue.wrappedValue)
                        elif value_type == 'area' and hasattr(prop.NominalValue, 'wrappedValue'):
                            return round(prop.NominalValue.wrappedValue, 3)
                        elif value_type == 'bool' and hasattr(prop.NominalValue, 'wrappedValue'):
                            return prop.NominalValue.wrappedValue
    return None

# MAIN
def main():
    # Paths
    csv_room_to_room = "Output01_RoomToRoom_BySeparationLine.csv"
    csv_doors = "Output02_RoomToRoom_ByDoors.csv"
    csv_windows = "Output03_RoomToRoom_ByWindows.csv"

    # Load config.yaml
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)

    ifc_file_path = config["ifc_file"]
    storey_name = config["storey_name"]

    # Open IFC file
    ifc_file = ifcopenshell.open(ifc_file_path)
    print("IFC file opened successfully.")

    # Load and filter Rooms
    all_spaces = ifc_file.by_type("IfcSpace")
    spaces = filter_ifcspaces_by_storey(all_spaces, storey_name)
    spaces = filter_spaces_by_name(spaces)

    # Verbindung zu Neo4j herstellen
    uri = "bolt://localhost:7687"
    driver = GraphDatabase.driver(uri, auth=("neo4j", "iaacthesis"))

    # Knoten in Neo4j erstellen und mit Daten anreichern
    create_ifcspace_nodes(driver, spaces)

    # Verbindungen zwischen Räumen erstellen
    process_direct_connections(driver, csv_room_to_room)
    process_element_connections(driver, csv_doors, "Door")
    process_element_connections(driver, csv_windows, "Window")

    # Verbindung schließen
    driver.close()
    print("IfcSpaces und Verbindungen wurden erfolgreich in Neo4j importiert.")

if __name__ == "__main__":
    main()
