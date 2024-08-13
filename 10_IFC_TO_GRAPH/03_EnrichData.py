import ifcopenshell
import pickle
import networkx as nx

# Funktion zum Laden der IFC-Datei
def load_ifc_file(file_path):
    return ifcopenshell.open(file_path)

# Funktion zum Laden des gespeicherten Graphen
def load_graph(pickle_file_path):
    with open(pickle_file_path, 'rb') as f:
        return pickle.load(f)

# Funktion zum Auslesen spezifischer Attribute eines IFC-Elements
def get_ifc_element_attributes(ifc_element, attributes):
    attr_data = {}
    for attr in attributes:
        if hasattr(ifc_element, attr):
            attr_data[attr] = getattr(ifc_element, attr)
        else:
            attr_data[attr] = None  # Falls das Attribut nicht existiert, None zuweisen
    return attr_data

# Hauptfunktion zum Anreichern des Graphen mit zusätzlichen Attributen
def enrich_graph_with_ifc_data(graph, ifc_file, attributes):
    # Durchlaufe alle Knoten im Graphen
    for node in graph.nodes(data=True):
        global_id = node[1].get('GlobalId')
        
        if global_id:
            # Suche das IFC-Element mit dem entsprechenden GlobalId
            ifc_element = ifc_file.by_guid(global_id)
            
            if ifc_element:
                # Extrahiere die gewünschten Attribute
                element_attributes = get_ifc_element_attributes(ifc_element, attributes)
                
                # Füge die Attribute zum Knoten hinzu
                for attr_name, attr_value in element_attributes.items():
                    graph.nodes[node[0]][attr_name] = attr_value

# Skript ausführen
if __name__ == "__main__":
    # Pfade zu den Dateien
    pickle_file_path = "network_graph.pkl"
    ifc_file_path = "Hus28_test.ifc"

    # Zu extrahierende Attribute (Beispiel: Name, ObjectType, Description)
    attributes_to_extract = ['Name', 'ObjectType', 'Description']

    # IFC-Datei und Graph laden
    ifc_file = load_ifc_file(ifc_file_path)
    G = load_graph(pickle_file_path)

    # Graphen mit IFC-Daten anreichern
    enrich_graph_with_ifc_data(G, ifc_file, attributes_to_extract)

    # Option: Den angereicherten Graphen wieder speichern
    with open('enriched_network_graph.pkl', 'wb') as f:
        pickle.dump(G, f)

    print("Graph wurde erfolgreich mit zusätzlichen Attributen angereichert.")
