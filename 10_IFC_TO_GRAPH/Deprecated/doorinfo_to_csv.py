import ifcopenshell
import csv

def main(ifc_file, all_doors, target_storey):

    # Initialize a dictionary to store doors and their connected rooms
    door_to_room = {}

    # Iterate over all IfcRelSpaceBoundary elements
    for rel in ifc_file.by_type("IfcRelSpaceBoundary"):
        # Check if the related element is a door
        if rel.RelatedBuildingElement in all_doors:
            door = rel.RelatedBuildingElement
            door_global_id = door.GlobalId
            
            # Check if the door is on the target storey
            door_storey = door.ContainedInStructure
            if door_storey and door_storey[0].RelatingStructure == target_storey:
                # Assign the room (IfcSpace) to the door
                room = rel.RelatingSpace
                if room:
                    room_global_id = room.GlobalId
                    if door_global_id in door_to_room:
                        door_to_room[door_global_id].append(room_global_id)
                    else:
                        door_to_room[door_global_id] = [room_global_id]

    if door_to_room:
        with open('Output02_RoomToRoom_ByDoors.csv', 'w', newline='') as csvfile:
            csvwriter = csv.writer(csvfile, delimiter=';')
            for door_global_id, room_global_ids in door_to_room.items():
                # Combine the room GUIDs into a single item separated by commas
                room_guids_combined = ",".join(room_global_ids)
                csvwriter.writerow([door_global_id, room_guids_combined])
        print("Data has been written to Output02_RoomToRoom_ByDoors.csv")
    else:
        print("door_to_room is empty, no data to write to CSV.")


if __name__ == "__main__":
    main()