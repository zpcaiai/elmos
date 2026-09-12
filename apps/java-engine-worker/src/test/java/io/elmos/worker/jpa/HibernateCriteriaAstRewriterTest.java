package io.elmos.worker.jpa;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class HibernateCriteriaAstRewriterTest {

    @Test
    @DisplayName("Rewrites Hibernate Criteria with Restrictions and list execution to JPA CriteriaQuery")
    void testBasicCriteriaRewrite() {
        String legacyCode = """
                package com.example.dao;

                import org.hibernate.Criteria;
                import org.hibernate.criterion.Restrictions;
                import org.hibernate.Session;
                import java.util.List;

                public class UserDao {
                    private Session session;

                    public List<User> findActiveUsers(String emailKeyword, int minAge) {
                        Criteria criteria = session.createCriteria(User.class);
                        criteria.add(Restrictions.eq("status", "ACTIVE"));
                        criteria.add(Restrictions.like("email", "%" + emailKeyword + "%"));
                        criteria.add(Restrictions.ge("age", minAge));
                        return criteria.list();
                    }
                }
                """;

        var result = HibernateCriteriaAstRewriter.rewrite(legacyCode);
        assertTrue(result.modified());
        assertTrue(result.rewriteCount() >= 4);

        String rewritten = result.rewrittenSource();
        // Verifies legacy imports removed
        assertFalse(rewritten.contains("import org.hibernate.Criteria;"));
        assertFalse(rewritten.contains("import org.hibernate.criterion.Restrictions;"));

        // Verifies JPA imports injected
        assertTrue(rewritten.contains("import jakarta.persistence.criteria.CriteriaBuilder;"));
        assertTrue(rewritten.contains("import jakarta.persistence.criteria.CriteriaQuery;"));
        assertTrue(rewritten.contains("import jakarta.persistence.criteria.Root;"));
        assertTrue(rewritten.contains("import jakarta.persistence.criteria.Predicate;"));

        // Verifies AST rewrites
        assertTrue(rewritten.contains("CriteriaBuilder cb = entityManager.getCriteriaBuilder();"));
        assertTrue(rewritten.contains("CriteriaQuery<User> cq = cb.createQuery(User.class);"));
        assertTrue(rewritten.contains("Root<User> root = cq.from(User.class);"));
        assertTrue(rewritten.contains("predicates.add(cb.equal(root.get(\"status\"), \"ACTIVE\"));"));
        assertTrue(rewritten.contains("predicates.add(cb.like(root.get(\"email\"), \"%\" + emailKeyword + \"%\"));"));
        assertTrue(rewritten.contains("predicates.add(cb.greaterThanOrEqualTo(root.get(\"age\"), minAge));"));
        assertTrue(rewritten.contains("cq.where(predicates.toArray(new Predicate[0]));"));
        assertTrue(rewritten.contains("entityManager.createQuery(cq).getResultList()"));
    }

    @Test
    @DisplayName("Rewrites Hibernate Criteria with Order and uniqueResult to JPA single result")
    void testCriteriaWithOrderAndUniqueResult() {
        String legacyCode = """
                package com.example.dao;

                import org.hibernate.Criteria;
                import org.hibernate.criterion.Restrictions;
                import org.hibernate.criterion.Order;

                public class OrderDao {
                    public OrderEntity findLatestOrder(Long customerId) {
                        Criteria criteria = session.createCriteria(OrderEntity.class);
                        criteria.add(Restrictions.eq("customerId", customerId));
                        criteria.addOrder(Order.desc("createTime"));
                        return (OrderEntity) criteria.uniqueResult();
                    }
                }
                """;

        var result = HibernateCriteriaAstRewriter.rewrite(legacyCode);
        assertTrue(result.modified());

        String rewritten = result.rewrittenSource();
        assertTrue(rewritten.contains("cq.orderBy(cb.desc(root.get(\"createTime\")));"));
        assertTrue(rewritten.contains("entityManager.createQuery(cq).getSingleResult()"));
    }

    @Test
    @DisplayName("Rewrites Hibernate Criteria with Projections rowCount")
    void testCriteriaWithProjectionRowCount() {
        String legacyCode = """
                package com.example.dao;

                import org.hibernate.Criteria;
                import org.hibernate.criterion.Restrictions;
                import org.hibernate.criterion.Projections;

                public class StatsDao {
                    public Long countUsers() {
                        Criteria criteria = session.createCriteria(User.class);
                        criteria.setProjection(Projections.rowCount());
                        criteria.add(Restrictions.eq("deleted", false));
                        return (Long) criteria.uniqueResult();
                    }
                }
                """;

        var result = HibernateCriteriaAstRewriter.rewrite(legacyCode);
        assertTrue(result.modified());

        String rewritten = result.rewrittenSource();
        assertTrue(rewritten.contains("cq.select(cb.count(root));"));
        assertTrue(rewritten.contains("predicates.add(cb.equal(root.get(\"deleted\"), false));"));
    }

    @Test
    @DisplayName("Rewrites Hibernate Criteria with composite Restrictions.or and createAlias")
    void testCriteriaWithCompositeOrAndAlias() {
        String legacyCode = """
                package com.example.dao;

                import org.hibernate.Criteria;
                import org.hibernate.criterion.Restrictions;

                public class EmployeeDao {
                    public List<Employee> findEmployees() {
                        Criteria criteria = session.createCriteria(Employee.class);
                        criteria.createAlias("department", "dept");
                        criteria.add(Restrictions.or(Restrictions.eq("status", "ACTIVE"), Restrictions.eq("status", "PENDING")));
                        criteria.add(Restrictions.isNotEmpty("projects"));
                        return criteria.list();
                    }
                }
                """;

        var result = HibernateCriteriaAstRewriter.rewrite(legacyCode);
        assertTrue(result.modified());

        String rewritten = result.rewrittenSource();
        assertTrue(rewritten.contains("Join<?, ?> dept = root.join(\"department\");"));
        assertTrue(rewritten.contains("cb.or(cb.equal(root.get(\"status\"), \"ACTIVE\"), cb.equal(root.get(\"status\"), \"PENDING\"))"));
        assertTrue(rewritten.contains("cb.isNotEmpty(root.get(\"projects\"))"));
        assertTrue(rewritten.contains("import jakarta.persistence.criteria.Join;"));
    }
}
