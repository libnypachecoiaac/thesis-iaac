import ifcopenshell
import pickle
import networkx as nx
import re

# Funktion zum Laden der IFC-Datei
def load_ifc_file(file_path):
    return ifcopenshell.open(file_path)

# Funktion zum Laden des gespeicherten Graphen
def load_graph(pickle_file_path):
    with open(pickle_file_path, 'rb') as f:
        return pickle.load(f)

# Funktion zum Dekodieren von Unicode-Sonderzeichen in IFC-TEXT
def decode_ifc_text(text):
    # Suche nach allen \X\HHHH Kodierungen im Text
    matches = re.findall(r'\\X\\([0-9A-Fa-f]{4})', text)
    for match in matches:
        # Ersetze die Kodierung durch das entsprechende Unicode-Zeichen
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

# Skript ausführen
if __name__ == "__main__":
    # Pfade zu den Dateien
    pickle_file_path = "enriched_network_graph.pkl"
    ifc_file_path = "Hus28_test.ifc"

    # IFC-Datei und Graph laden
    ifc_file = load_ifc_file(ifc_file_path)
    G = load_graph(pickle_file_path)

    # Graphen mit IfcWindow-Daten anreichern
    enrich_graph_with_ifcwindow_data(G, ifc_file)

    # Optional: Den angereicherten Graphen wieder speichern
    with open('enriched_network_graph_with_windows.pkl', 'wb') as f:
        pickle.dump(G, f)

    print("Graph wurde erfolgreich mit IfcWindow-Attributen angereichert.")
