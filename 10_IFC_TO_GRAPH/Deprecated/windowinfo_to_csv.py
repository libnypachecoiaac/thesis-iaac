import ifcopenshell
import csv

def get_storey(element):
    # Find the IfcBuildingStorey for the given element
    for rel in element.ContainedInStructure:
        if rel.is_a("IfcRelContainedInSpatialStructure") and rel.RelatingStructure.is_a("IfcBuildingStorey"):
            return rel.RelatingStructure
    return None

def main(ifc_file, ifc_windows, target_storey):

    # Initialize a dictionary to store windows and their connected rooms
    window_to_room = {}

    # Iterate over all IfcRelSpaceBoundary elements
    for rel in ifc_file.by_type("IfcRelSpaceBoundary"):
        # Check if the related element is a window
        if rel.RelatedBuildingElement in ifc_windows:
            window = rel.RelatedBuildingElement
            window_guid = window.GlobalId
            
            # Check if the window is on the target storey
            window_storey = get_storey(window)
            if window_storey == target_storey:
                # Assign the room (IfcSpace) to the window
                room = rel.RelatingSpace
                if room:
                    room_guid = room.GlobalId
                    if window_guid not in window_to_room:
                        window_to_room[window_guid] = []
                    window_to_room[window_guid].append(room_guid)

    # Write the results to a CSV file
    with open('Output03_RoomToRoom_ByWindows.csv', 'w', newline='') as csvfile:
        csvwriter = csv.writer(csvfile, delimiter=';')
        for window_guid, room_guids in window_to_room.items():
            row = [window_guid, ",".join(room_guids)]
            csvwriter.writerow(row)

    print("Results have been saved to Output03_RoomToRoom_ByWindows.csv")

if __name__ == "__main__":
    main()
