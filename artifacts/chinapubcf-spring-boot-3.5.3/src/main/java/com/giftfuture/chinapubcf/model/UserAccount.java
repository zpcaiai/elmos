package com.giftfuture.chinapubcf.model;

public record UserAccount(
        long userId,
        String name,
        String email,
        String passwordHash,
        String status,
        String admireField,
        String expertAt,
        String tag,
        String knowFrom) {
    public PublicView publicView() {
        return new PublicView(userId, name, email, status, admireField, expertAt, tag, knowFrom);
    }

    public record PublicView(
            long userId,
            String name,
            String email,
            String status,
            String admireField,
            String expertAt,
            String tag,
            String knowFrom) {
    }
}
