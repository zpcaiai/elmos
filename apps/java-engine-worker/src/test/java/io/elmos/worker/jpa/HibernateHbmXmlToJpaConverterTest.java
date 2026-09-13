package io.elmos.worker.jpa;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class HibernateHbmXmlToJpaConverterTest {
    @TempDir Path root;

    @Test void convertsSupportedScalarAndRelationMappings() throws Exception {
        Path mapping = root.resolve("Order.hbm.xml");
        Files.writeString(mapping, """
                <hibernate-mapping package="com.acme.orders">
                  <class name="Order" table="legacy_order">
                    <id name="id" type="long" column="order_id"><generator class="identity"/></id>
                    <property name="total" type="big_decimal" column="order_total"/>
                    <many-to-one name="customer" class="com.acme.Customer" column="customer_id"/>
                  </class>
                </hibernate-mapping>
                """);
        Path output = root.resolve("generated");
        var result = HibernateHbmXmlToJpaConverter.convert(root, output);
        assertTrue(result.modified());
        assertTrue(result.blockingObligations().isEmpty());
        String source = Files.readString(output.resolve("com/acme/orders/Order.java"));
        assertTrue(source.contains("@Entity"));
        assertTrue(source.contains("@Table(name = \"legacy_order\")"));
        assertTrue(source.contains("private java.math.BigDecimal total"));
        assertTrue(source.contains("@ManyToOne(fetch = FetchType.LAZY, optional = false)"));
    }

    @Test void blocksDoctypeAndCompositeIdsWithoutWritingEntity() throws Exception {
        Files.writeString(root.resolve("Unsafe.hbm.xml"), """
                <!DOCTYPE x [<!ENTITY leak SYSTEM "file:///etc/passwd">]>
                <hibernate-mapping><class name="Unsafe"><id name="id" type="long"/></class></hibernate-mapping>
                """);
        Files.writeString(root.resolve("Composite.hbm.xml"), """
                <hibernate-mapping package="com.acme"><class name="Composite"><composite-id/></class></hibernate-mapping>
                """);
        Path output = root.resolve("generated");
        var result = HibernateHbmXmlToJpaConverter.convert(root, output);
        assertFalse(result.blockingObligations().isEmpty());
        assertFalse(Files.exists(output.resolve("com/acme/Composite.java")));
    }
}
