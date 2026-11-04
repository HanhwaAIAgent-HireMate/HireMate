FROM eclipse-temurin:25-jdk AS build
WORKDIR /app/backend
COPY backend/gradle ./gradle
COPY backend/gradlew backend/build.gradle backend/settings.gradle ./
RUN --mount=type=cache,target=/root/.gradle ./gradlew --version
COPY backend/src ./src
RUN --mount=type=cache,target=/root/.gradle ./gradlew --no-daemon bootJar

FROM eclipse-temurin:25-jre
WORKDIR /app
COPY --from=build /app/backend/build/libs/*-SNAPSHOT.jar app.jar
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
