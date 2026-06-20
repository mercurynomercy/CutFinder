import Foundation

/// Lifecycle state of the local backend server, used to drive menu enablement
/// and the window's three-state view (installing / running / error).
public enum ServerState: Equatable {
    case idle
    case installing
    case starting
    case running
    case stopped
    case error(String)
}
