import ifcopenshell
import pickle
import networkx as nx
import re
from pyvis.network import Network

# Funktion zum Laden der IFC-Datei
def load_ifc_file(file_path):
    return ifcopenshell.open(file_path)

# Funktion zum Laden des gespeicherten Graphen
def load_graph(pickle_file_path):
    with open(pickle_file_path, 'rb') as f:
        return pickle.load(f)

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
    return None

# Hauptfunktion zum Anreichern des Graphen mit IfcWindow-Daten
def enrich_graph_with_ifcwindow_data(graph, ifc_file):
    for node in graph.nodes(data=True):
        # Prüfe, ob der Node ein IfcWindow ist
        if node[0].startswith("Window_"):
            # Setze das Object-Attribut
            graph.nodes[node[0]]['Object'] = 'Window'
            
            # Hole das GlobalId-Attribut
            global_id = node[1].get('GlobalId')
            
            if global_id:
                # Suche das IfcWindow-Element in der IFC-Datei
                ifc_window = ifc_file.by_guid(global_id)
                
                if ifc_window:
                    # Extrahiere die benötigten Eigenschaften
                    graph.nodes[node[0]]['Construction Type'] = extract_property_value(ifc_window, 'Construction Type', 'text')
                    graph.nodes[node[0]]['Sill Height'] = extract_property_value(ifc_window, 'Sill Height', 'number')
                    graph.nodes[node[0]]['Height'] = extract_property_value(ifc_window, 'Height', 'number')
                    graph.nodes[node[0]]['Width'] = extract_property_value(ifc_window, 'Width', 'number')
                    graph.nodes[node[0]]['Area'] = extract_property_value(ifc_window, 'Area', 'area')
                    graph.nodes[node[0]]['Material Interior'] = extract_property_value(ifc_window, 'Material Interior', 'text')
                    graph.nodes[node[0]]['Material Exterior'] = extract_property_value(ifc_window, 'Material Exterior', 'text')
                    graph.nodes[node[0]]['Type'] = extract_property_value(ifc_window, 'Family and Type', 'text')


# Funktion, um die Attribute eines Knotens auszugeben
def print_node_attributes(graph, node_name):
    if node_name in graph.nodes:
        attributes = graph.nodes[node_name]
        print(f"Attributes of node '{node_name}':")
        for attr_name, attr_value in attributes.items():
            print(f"  {attr_name}: {attr_value}")
    else:
        print(f"Node '{node_name}' not found in the graph.")

# Funktion zur Visualisierung des Graphen mit Pyvis
def visualize_graph(graph, output_file="interactive_graph.html"):
    net = Network(notebook=False, height="800px", width="100%", select_menu=True, filter_menu=True)
    net.from_nx(graph)

    # Farbe und Tooltip-Informationen für die IfcWindow-Nodes setzen
    for node in net.nodes:
        node_data = graph.nodes[node['id']]
        if node['id'].startswith("Window_"):
            tooltip = f"GlobalId: {node_data.get('GlobalId', 'N/A')}<br>"
            tooltip += f"Object: {node_data.get('Object', 'N/A')}<br>"
            tooltip += f"Construction Type: {node_data.get('Construction Type', 'N/A')}<br>"
            tooltip += f"Sill Height: {node_data.get('Sill Height', 'N/A')}<br>"
            tooltip += f"Height: {node_data.get('Height', 'N/A')}<br>"
            tooltip += f"Width: {node_data.get('Width', 'N/A')}<br>"
            tooltip += f"Area: {node_data.get('Area', 'N/A')}<br>"
            tooltip += f"Material Interior: {node_data.get('Material Interior', 'N/A')}<br>"
            tooltip += f"Material Exterior: {node_data.get('Material Exterior', 'N/A')}<br>"
            tooltip += f"Type: {node_data.get('Type', 'N/A')}"
            node['title'] = tooltip
        else:
            # Lösche eventuell vorhandene, ungewollte Attribute
            node.pop('title', None)

    # HTML-Datei erstellen und anzeigen
    net.write_html(output_file)
    print(f"Graph wurde erfolgreich visualisiert und in {output_file} gespeichert.")

# Skript ausführen
if __name__ == "__main__":
    # Pfade zu den Dateien
    pickle_file_path = "network_graph.pkl"
    ifc_file_path = "Hus28_test.ifc"

    # IFC-Datei und Graph laden
    ifc_file = load_ifc_file(ifc_file_path)
    G = load_graph(pickle_file_path)

    # Graphen mit IfcWindow-Daten anreichern
    enrich_graph_with_ifcwindow_data(G, ifc_file)

    # Den angereicherten Graphen visualisieren
    visualize_graph(G, "interactive_graph_with_windows.html")

    print("END")

    # Beispielaufruf der Funktion
    print_node_attributes(G, "Window_56636")
