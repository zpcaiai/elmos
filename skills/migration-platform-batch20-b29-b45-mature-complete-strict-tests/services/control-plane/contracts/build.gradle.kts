plugins { `java-library` }

java { toolchain { languageVersion = JavaLanguageVersion.of(21) } }

dependencies {
    api("jakarta.validation:jakarta.validation-api:3.1.1")
}

tasks.test { useJUnitPlatform() }
