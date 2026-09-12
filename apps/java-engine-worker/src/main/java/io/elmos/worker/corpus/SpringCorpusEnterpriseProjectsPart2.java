package io.elmos.worker.corpus;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Rich enterprise scenario specifications for Benchmark Projects 11 through 20.
 */
public final class SpringCorpusEnterpriseProjectsPart2 {

    private SpringCorpusEnterpriseProjectsPart2() {}

    public static Map<String, String> getFilesForProject(int index, String id, String bootVer, String javaVer) {
        Map<String, String> files = new LinkedHashMap<>();
        switch (index) {
            case 11 -> populateFinanceAccountingLedger(files, id, bootVer, javaVer);
            case 12 -> populateIotDeviceTelemetry(files, id, bootVer, javaVer);
            case 13 -> populateHealthcareEmrRecords(files, id, bootVer, javaVer);
            case 14 -> populateLogisticsFleetDispatch(files, id, bootVer, javaVer);
            case 15 -> populateCloudConfigBootstrap(files, id, bootVer, javaVer);
            case 16 -> populateLegacySpringMvcWarPortal(files, id, bootVer, javaVer);
            case 17 -> populateGradleEnterpriseMonolith(files, id, bootVer, javaVer);
            case 18 -> populateOAuth2ResourceServerSso(files, id, bootVer, javaVer);
            case 19 -> populateHibernateLegacyCriteriaCrm(files, id, bootVer, javaVer);
            case 20 -> populateCloudGatewaySecurityMesh(files, id, bootVer, javaVer);
            default -> {}
        }
        return files;
    }

    private static void populateFinanceAccountingLedger(Map<String, String> files, String id, String bootVer, String javaVer) {
        files.put("src/main/java/io/elmos/benchmark/finance/domain/JournalEntry.java", """
                package io.elmos.benchmark.finance.domain;

                import javax.persistence.*;
                import java.math.BigDecimal;
                import java.time.LocalDate;
                import org.hibernate.annotations.Type;

                @Entity
                @Table(name = "journal_entries")
                public class JournalEntry {
                    @Id
                    @GeneratedValue(strategy = GenerationType.IDENTITY)
                    private Long id;

                    @Column(nullable = false)
                    private String entryNumber;

                    @Column(nullable = false)
                    private String debitAccount;

                    @Column(nullable = false)
                    private String creditAccount;

                    @Column(nullable = false, precision = 18, scale = 4)
                    private BigDecimal amount;

                    private LocalDate postingDate;

                    @Type(type = "json")
                    private String auditMetadata;

                    public Long getId() { return id; }
                    public void setId(Long id) { this.id = id; }
                    public String getEntryNumber() { return entryNumber; }
                    public void setEntryNumber(String num) { this.entryNumber = num; }
                    public String getDebitAccount() { return debitAccount; }
                    public void setDebitAccount(String acc) { this.debitAccount = acc; }
                    public String getCreditAccount() { return creditAccount; }
                    public void setCreditAccount(String acc) { this.creditAccount = acc; }
                    public BigDecimal getAmount() { return amount; }
                    public void setAmount(BigDecimal amount) { this.amount = amount; }
                    public LocalDate getPostingDate() { return postingDate; }
                    public void setPostingDate(LocalDate date) { this.postingDate = date; }
                    public String getAuditMetadata() { return auditMetadata; }
                    public void setAuditMetadata(String meta) { this.auditMetadata = meta; }
                }
                """);

        files.put("src/main/java/io/elmos/benchmark/finance/repository/JournalEntryRepository.java", """
                package io.elmos.benchmark.finance.repository;

                import io.elmos.benchmark.finance.domain.JournalEntry;
                import org.springframework.data.jpa.repository.JpaRepository;
                import org.springframework.data.jpa.repository.Query;
                import java.time.LocalDate;
                import java.util.List;

                public interface JournalEntryRepository extends JpaRepository<JournalEntry, Long> {
                    @Query("SELECT j FROM JournalEntry j WHERE j.postingDate >= ? AND j.debitAccount = ?")
                    List<JournalEntry> findRecentEntriesByAccount(LocalDate since, String account);
                }
                """);
    }

    private static void populateIotDeviceTelemetry(Map<String, String> files, String id, String bootVer, String javaVer) {
        files.put("src/main/java/io/elmos/benchmark/iot/domain/DeviceTelemetryReading.java", """
                package io.elmos.benchmark.iot.domain;

                import javax.persistence.*;
                import java.time.Instant;
                import org.hibernate.annotations.Type;

                @Entity
                @Table(name = "device_telemetry")
                public class DeviceTelemetryReading {
                    @Id
                    @GeneratedValue(strategy = GenerationType.IDENTITY)
                    private Long id;

                    @Column(nullable = false)
                    private String deviceId;

                    private Double temperature;
                    private Double pressure;

                    @Type(type = "json")
                    private String sensorPayload;

                    private Instant recordedAt;

                    public Long getId() { return id; }
                    public void setId(Long id) { this.id = id; }
                    public String getDeviceId() { return deviceId; }
                    public void setDeviceId(String devId) { this.deviceId = devId; }
                    public Double getTemperature() { return temperature; }
                    public void setTemperature(Double temp) { this.temperature = temp; }
                    public Double getPressure() { return pressure; }
                    public void setPressure(Double press) { this.pressure = press; }
                    public String getSensorPayload() { return sensorPayload; }
                    public void setSensorPayload(String p) { this.sensorPayload = p; }
                    public Instant getRecordedAt() { return recordedAt; }
                    public void setRecordedAt(Instant t) { this.recordedAt = t; }
                }
                """);
        files.put("src/main/java/io/elmos/benchmark/iot/domain/TelemetryDataPoint.java", """
                package io.elmos.benchmark.iot.domain;

                import javax.persistence.*;
                import java.time.Instant;
                import org.hibernate.annotations.Type;

                @Entity
                @Table(name = "telemetry_data_points")
                public class TelemetryDataPoint {
                    @Id
                    @GeneratedValue(strategy = GenerationType.IDENTITY)
                    private Long id;

                    @Column(nullable = false)
                    private String deviceId;

                    private String metricType;
                    private Double readingValue;

                    private Instant timestamp;

                    @Type(type = "json")
                    private String metadata;

                    public Long getId() { return id; }
                    public void setId(Long id) { this.id = id; }
                    public String getDeviceId() { return deviceId; }
                    public void setDeviceId(String deviceId) { this.deviceId = deviceId; }
                    public String getMetricType() { return metricType; }
                    public void setMetricType(String metricType) { this.metricType = metricType; }
                    public Double getReadingValue() { return readingValue; }
                    public void setReadingValue(Double readingValue) { this.readingValue = readingValue; }
                    public Instant getTimestamp() { return timestamp; }
                    public void setTimestamp(Instant timestamp) { this.timestamp = timestamp; }
                    public String getMetadata() { return metadata; }
                    public void setMetadata(String metadata) { this.metadata = metadata; }
                }
                """);
    }

    private static void populateHealthcareEmrRecords(Map<String, String> files, String id, String bootVer, String javaVer) {
        files.put("src/main/java/io/elmos/benchmark/healthcare/domain/MedicalEncounter.java", """
                package io.elmos.benchmark.healthcare.domain;

                import javax.persistence.*;
                import java.time.LocalDateTime;
                import org.hibernate.annotations.Type;

                @Entity
                @Table(name = "medical_encounters")
                public class MedicalEncounter {
                    @Id
                    @GeneratedValue(strategy = GenerationType.IDENTITY)
                    private Long id;

                    @Column(nullable = false)
                    private String patientMrn;

                    private String practitionerNpi;
                    private LocalDateTime encounterDate;

                    @Type(type = "json")
                    private String clinicalObservations;

                    public Long getId() { return id; }
                    public void setId(Long id) { this.id = id; }
                    public String getPatientMrn() { return patientMrn; }
                    public void setPatientMrn(String mrn) { this.patientMrn = mrn; }
                    public String getPractitionerNpi() { return practitionerNpi; }
                    public void setPractitionerNpi(String npi) { this.practitionerNpi = npi; }
                    public LocalDateTime getEncounterDate() { return encounterDate; }
                    public void setEncounterDate(LocalDateTime d) { this.encounterDate = d; }
                    public String getClinicalObservations() { return clinicalObservations; }
                    public void setClinicalObservations(String obs) { this.clinicalObservations = obs; }
                }
                """);
        files.put("src/main/java/io/elmos/benchmark/healthcare/domain/PatientRecord.java", """
                package io.elmos.benchmark.healthcare.domain;

                import javax.persistence.*;
                import java.time.LocalDate;
                import org.hibernate.annotations.Type;

                @Entity
                @Table(name = "patient_records")
                public class PatientRecord {
                    @Id
                    @GeneratedValue(strategy = GenerationType.IDENTITY)
                    private Long id;

                    @Column(nullable = false, unique = true)
                    private String mrn;

                    @Column(nullable = false)
                    private String fullName;

                    private LocalDate dateOfBirth;
                    private String bloodGroup;

                    @Type(type = "json")
                    private String encryptedMedicalNotes;

                    public Long getId() { return id; }
                    public void setId(Long id) { this.id = id; }
                    public String getMrn() { return mrn; }
                    public void setMrn(String mrn) { this.mrn = mrn; }
                    public String getFullName() { return fullName; }
                    public void setFullName(String fullName) { this.fullName = fullName; }
                    public LocalDate getDateOfBirth() { return dateOfBirth; }
                    public void setDateOfBirth(LocalDate dateOfBirth) { this.dateOfBirth = dateOfBirth; }
                    public String getBloodGroup() { return bloodGroup; }
                    public void setBloodGroup(String bloodGroup) { this.bloodGroup = bloodGroup; }
                    public String getEncryptedMedicalNotes() { return encryptedMedicalNotes; }
                    public void setEncryptedMedicalNotes(String encryptedMedicalNotes) { this.encryptedMedicalNotes = encryptedMedicalNotes; }
                }
                """);
    }

    private static void populateLogisticsFleetDispatch(Map<String, String> files, String id, String bootVer, String javaVer) {
        files.put("src/main/java/io/elmos/benchmark/logistics/domain/ShipmentWaybill.java", """
                package io.elmos.benchmark.logistics.domain;

                import javax.persistence.*;
                import java.time.Instant;
                import org.hibernate.annotations.Type;

                @Entity
                @Table(name = "shipment_waybills")
                public class ShipmentWaybill {
                    @Id
                    @GeneratedValue(strategy = GenerationType.IDENTITY)
                    private Long id;

                    @Column(nullable = false, unique = true)
                    private String trackingCode;

                    private String originHub;
                    private String destinationHub;

                    @Type(type = "json")
                    private String routeWaypoints;

                    public Long getId() { return id; }
                    public void setId(Long id) { this.id = id; }
                    public String getTrackingCode() { return trackingCode; }
                    public void setTrackingCode(String c) { this.trackingCode = c; }
                    public String getOriginHub() { return originHub; }
                    public void setOriginHub(String o) { this.originHub = o; }
                    public String getDestinationHub() { return destinationHub; }
                    public void setDestinationHub(String d) { this.destinationHub = d; }
                    public String getRouteWaypoints() { return routeWaypoints; }
                    public void setRouteWaypoints(String r) { this.routeWaypoints = r; }
                }
                """);
        files.put("src/main/java/io/elmos/benchmark/logistics/domain/FleetVehicle.java", """
                package io.elmos.benchmark.logistics.domain;

                import javax.persistence.*;
                import org.hibernate.annotations.Type;

                @Entity
                @Table(name = "fleet_vehicles")
                public class FleetVehicle {
                    @Id
                    @GeneratedValue(strategy = GenerationType.IDENTITY)
                    private Long id;

                    @Column(nullable = false, unique = true)
                    private String vin;

                    @Column(nullable = false)
                    private String fleetCode;

                    private String currentStatus;
                    private Integer capacityKg;

                    @Type(type = "json")
                    private String telemetryData;

                    public Long getId() { return id; }
                    public void setId(Long id) { this.id = id; }
                    public String getVin() { return vin; }
                    public void setVin(String vin) { this.vin = vin; }
                    public String getFleetCode() { return fleetCode; }
                    public void setFleetCode(String fleetCode) { this.fleetCode = fleetCode; }
                    public String getCurrentStatus() { return currentStatus; }
                    public void setCurrentStatus(String currentStatus) { this.currentStatus = currentStatus; }
                    public Integer getCapacityKg() { return capacityKg; }
                    public void setCapacityKg(Integer capacityKg) { this.capacityKg = capacityKg; }
                    public String getTelemetryData() { return telemetryData; }
                    public void setTelemetryData(String telemetryData) { this.telemetryData = telemetryData; }
                }
                """);
    }

    private static void populateCloudConfigBootstrap(Map<String, String> files, String id, String bootVer, String javaVer) {
        files.put("src/main/resources/bootstrap.yml", """
                spring:
                  application:
                    name: cloud-config-bootstrap-service
                  cloud:
                    config:
                      uri: http://config-server:8888
                      fail-fast: true
                """);
    }

    private static void populateLegacySpringMvcWarPortal(Map<String, String> files, String id, String bootVer, String javaVer) {
        files.put("src/main/resources/spring-mvc-portal.xml", """
                <?xml version="1.0" encoding="UTF-8"?>
                <beans xmlns="http://www.springframework.org/schema/beans"
                       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                       xmlns:context="http://www.springframework.org/schema/context"
                       xmlns:mvc="http://www.springframework.org/schema/mvc"
                       xsi:schemaLocation="
                           http://www.springframework.org/schema/beans http://www.springframework.org/schema/beans/spring-beans.xsd
                           http://www.springframework.org/schema/context http://www.springframework.org/schema/context/spring-context.xsd
                           http://www.springframework.org/schema/mvc http://www.springframework.org/schema/mvc/spring-mvc.xsd">

                    <context:component-scan base-package="io.elmos.benchmark.portal" />
                    <mvc:annotation-driven />

                    <bean id="portalViewResolver" class="io.elmos.benchmark.portal.PortalViewResolver">
                        <property name="prefix" value="/WEB-INF/jsp/" />
                        <property name="suffix" value=".jsp" />
                    </bean>
                </beans>
                """);

        files.put("src/main/java/io/elmos/benchmark/portal/PortalViewResolver.java", """
                package io.elmos.benchmark.portal;

                public class PortalViewResolver {
                    private String prefix;
                    private String suffix;
                    public String getPrefix() { return prefix; }
                    public void setPrefix(String p) { this.prefix = p; }
                    public String getSuffix() { return suffix; }
                    public void setSuffix(String s) { this.suffix = s; }
                }
                """);
    }

    private static void populateGradleEnterpriseMonolith(Map<String, String> files, String id, String bootVer, String javaVer) {
        files.put("src/main/java/io/elmos/benchmark/monolith/MonolithSecurityConfig.java", """
                package io.elmos.benchmark.monolith;

                import org.springframework.context.annotation.Configuration;
                import org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter;
                import org.springframework.security.config.annotation.web.builders.HttpSecurity;

                @Configuration
                public class MonolithSecurityConfig extends WebSecurityConfigurerAdapter {
                    @Override
                    protected void configure(HttpSecurity http) throws Exception {
                        http.csrf().disable()
                            .authorizeRequests()
                            .antMatchers("/health").permitAll()
                            .anyRequest().authenticated();
                    }
                }
                """);
    }

    private static void populateOAuth2ResourceServerSso(Map<String, String> files, String id, String bootVer, String javaVer) {
        files.put("src/main/java/io/elmos/benchmark/oauth2/OAuth2SsoConfig.java", """
                package io.elmos.benchmark.oauth2;

                import org.springframework.context.annotation.Configuration;
                import org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter;
                import org.springframework.security.config.annotation.web.builders.HttpSecurity;

                @Configuration
                public class OAuth2SsoConfig extends WebSecurityConfigurerAdapter {
                    @Override
                    protected void configure(HttpSecurity http) throws Exception {
                        http.authorizeRequests()
                            .antMatchers("/oauth/token").permitAll()
                            .anyRequest().authenticated();
                    }
                }
                """);
    }

    private static void populateHibernateLegacyCriteriaCrm(Map<String, String> files, String id, String bootVer, String javaVer) {
        files.put("src/main/java/io/elmos/benchmark/crm/LegacyCriteriaSearchDao.java", """
                package io.elmos.benchmark.crm;

                import org.hibernate.Criteria;

                public class LegacyCriteriaSearchDao {
                    public void search(Criteria criteria) {
                    }
                }
                """);
    }

    private static void populateCloudGatewaySecurityMesh(Map<String, String> files, String id, String bootVer, String javaVer) {
        files.put("src/main/java/io/elmos/benchmark/mesh/MeshZuulFilter.java", """
                package io.elmos.benchmark.mesh;

                import com.netflix.zuul.ZuulFilter;
                import org.springframework.cloud.netflix.zuul.EnableZuulProxy;
                import org.springframework.context.annotation.Configuration;

                @Configuration
                @EnableZuulProxy
                public class MeshZuulFilter extends ZuulFilter {
                    public String filterType() { return "route"; }
                    public int filterOrder() { return 2; }
                    public boolean shouldFilter() { return true; }
                    public Object run() { return null; }
                }
                """);
    }
}
