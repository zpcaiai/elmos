package com.acme;

import javax.persistence.EntityManager;
import javax.transaction.Transactional;

public class LegacyOrderService {
    private final EntityManager entityManager;

    public LegacyOrderService(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Transactional
    private Object findOrder(String table, long id) {
        return entityManager.createNativeQuery("select * from " + table + " where id=" + id).getSingleResult();
    }
}
