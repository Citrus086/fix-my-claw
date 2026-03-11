import Foundation

struct PersistedNotificationEventStore: Decodable {
    let events: [PersistedNotificationEvent]
}

struct PersistedNotificationEvent: Decodable {
    let sequence: Int
    let eventId: String
    let timestamp: Double
    let kind: String
    let source: String
    let level: String?
    let messageText: String?
    let localTitle: String?
    let localBody: String?
    let dedupeKey: String?
    let channel: RepairNotificationPayload?

    enum CodingKeys: String, CodingKey {
        case sequence
        case eventId = "event_id"
        case timestamp
        case kind
        case source
        case level
        case messageText = "message_text"
        case localTitle = "local_title"
        case localBody = "local_body"
        case dedupeKey = "dedupe_key"
        case channel
    }
}
