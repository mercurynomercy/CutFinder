// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "CutFinder",
    platforms: [
        .macOS(.v13)
    ],
    targets: [
        .target(
            name: "CutFinderCore"
        ),
        .executableTarget(
            name: "CutFinder",
            dependencies: ["CutFinderCore"]
        ),
        .testTarget(
            name: "CutFinderCoreTests",
            dependencies: ["CutFinderCore"]
        ),
    ]
)
