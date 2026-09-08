/**
 * Usage: requireRole('admin', 'estimator')
 * Must run after requireAuth so req.user is populated.
 */
export function requireRole(...allowedRoles) {
  return (req, res, next) => {
    if (!req.user) {
      return res.status(401).json({ error: 'Not authenticated.' });
    }
    if (!allowedRoles.includes(req.user.role)) {
      return res.status(403).json({
        error: `This action requires one of these roles: ${allowedRoles.join(', ')}.`,
      });
    }
    next();
  };
}
