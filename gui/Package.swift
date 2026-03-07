// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "fix-my-claw-gui",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "fix-my-claw-gui", targets: ["FixMyClawGUI"])
    ],
    dependencies: [],
    targets: [
        .executableTarget(
            name: "FixMyClawGUI",
            swiftSettings: [.enableExperimentalFeature("StrictConcurrency")]
        )
    ]
)
