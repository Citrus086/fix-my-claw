import AppKit

@main
enum FixMyClawGUIApp {
    @MainActor
    private static let controller = MenuBarController()

    @MainActor
    static func main() {
        let application = NSApplication.shared
        application.setActivationPolicy(.accessory)
        application.delegate = controller
        application.run()
    }
}
